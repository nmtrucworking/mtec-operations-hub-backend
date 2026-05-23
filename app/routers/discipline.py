from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import config
from app.core.audit import create_audit_log
from app.core.discipline_levels import (
    DISCIPLINE_LEVEL_LABELS,
    DISCIPLINE_LEVEL_NONE,
    discipline_level_aliases,
    normalize_discipline_level,
)
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import (
    DisciplineRecord,
    User,
)
from app.schemas import DisciplineRecordCreate, DisciplineRecordUpdate
from app.utils import sanitize_pagination

router = APIRouter(prefix="/discipline-records", tags=["discipline"])


def _discipline_alias_filter(level: str) -> list[str]:
    return sorted({str(value).lower() for value in discipline_level_aliases(level)})


def _normalized_level_column():
    return func.lower(DisciplineRecord.discipline_level)


def _apply_legacy_deprecation_header(response: Response) -> None:
    if config.DISCIPLINE_LEGACY_DEPRECATION_HEADER:
        response.headers["X-MTEC-Deprecated"] = "true"
        response.headers["X-MTEC-Replacement"] = "/api/v2/evaluations"


def _ensure_legacy_mutation_allowed(response: Response) -> None:
    _apply_legacy_deprecation_header(response)
    if config.DISCIPLINE_LEGACY_READ_ONLY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DISCIPLINE_LEGACY_READ_ONLY",
                "message": "Discipline legacy module is read-only. Use /api/v2/evaluations instead.",
            },
        )


def _record_out(record: DisciplineRecord) -> dict:
    try:
        discipline_level = normalize_discipline_level(record.discipline_level)
    except ValueError:
        discipline_level = record.discipline_level
    return {
        "id": record.id,
        "memberId": record.member_id,
        "mssv": record.mssv,
        "name": record.name,
        "committee": record.committee,
        "absents": record.absents,
        "kpi": record.kpi,
        "disciplineLevel": discipline_level,
        "disciplineLevelLabel": DISCIPLINE_LEVEL_LABELS.get(
            discipline_level, record.discipline_level
        ),
        "note": record.note,
        "updatedBy": record.updated_by,
        "updatedAt": record.updated_at,
    }


@router.get("")
def list_records(
    response: Response,
    search: str | None = None,
    disciplineLevel: str | None = None,
    committee: str | None = None,
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    _apply_legacy_deprecation_header(response)
    page, pageSize = sanitize_pagination(page, pageSize)
    stmt = select(DisciplineRecord)
    count_stmt = select(func.count()).select_from(DisciplineRecord)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (DisciplineRecord.name.ilike(pattern))
            | (DisciplineRecord.mssv.ilike(pattern))
        )
        count_stmt = count_stmt.where(
            (DisciplineRecord.name.ilike(pattern))
            | (DisciplineRecord.mssv.ilike(pattern))
        )

    if disciplineLevel:
        canonical_level = normalize_discipline_level(disciplineLevel)
        aliases = _discipline_alias_filter(canonical_level)
        stmt = stmt.where(_normalized_level_column().in_(aliases))
        count_stmt = count_stmt.where(_normalized_level_column().in_(aliases))

    if committee:
        stmt = stmt.where(DisciplineRecord.committee == committee)
        count_stmt = count_stmt.where(DisciplineRecord.committee == committee)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.offset((page - 1) * pageSize).limit(pageSize)).all()
    return api_response(
        data=[_record_out(row) for row in rows],
        meta={"page": page, "pageSize": pageSize, "total": total},
    )


@router.get("/stats")
def get_stats(
    response: Response,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    _apply_legacy_deprecation_header(response)
    # Tổng số bản ghi (mỗi bản ghi tương ứng 1 thành viên có record kỷ luật/KPI)
    total_records = db.scalar(select(func.count()).select_from(DisciplineRecord)) or 0

    # Số ca cảnh cáo (giả sử level không phải 'Khong')
    no_level_aliases = _discipline_alias_filter(DISCIPLINE_LEVEL_NONE)
    warned_cases = (
        db.scalar(
            select(func.count())
            .select_from(DisciplineRecord)
            .where(_normalized_level_column().not_in(no_level_aliases))
        )
        or 0
    )

    # KPI trung bình
    avg_kpi = db.scalar(select(func.avg(DisciplineRecord.kpi))) or 0

    return api_response(
        data={
            "totalMembers": total_records,
            "warnedCases": warned_cases,
            "averageKPI": round(float(avg_kpi), 2),
        }
    )


@router.post("")
def create_record(
    body: DisciplineRecordCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_legacy_mutation_allowed(response)
    if not current_user.has_any_roles({"bcn", "bvh_discipline"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Khong co quyen tao discipline record",
        )

    record = DisciplineRecord(
        member_id=body.memberId,
        mssv=body.mssv,
        name=body.name,
        committee=body.committee,
        absents=body.absents,
        kpi=body.kpi,
        discipline_level=body.disciplineLevel,
        note=body.note,
        updated_by=current_user.full_name,
    )
    db.add(record)
    db.flush()
    create_audit_log(
        db=db,
        action="CREATE_DISCIPLINE_RECORD",
        resource_type="discipline",
        resource_id=record.id,
        actor=current_user,
        after_snapshot={
            "mssv": record.mssv,
            "name": record.name,
            "discipline_level": record.discipline_level,
            "kpi": record.kpi,
        },
    )
    db.commit()
    db.refresh(record)
    return api_response(data=_record_out(record))


@router.patch("/{record_id}")
def update_record(
    record_id: str,
    body: DisciplineRecordUpdate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_legacy_mutation_allowed(response)
    if not current_user.has_any_roles({"bcn", "bvh_discipline"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Khong co quyen cap nhat discipline record",
        )

    record = db.get(DisciplineRecord, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Khong tim thay discipline record",
        )

    payload = body.model_dump(exclude_none=True)
    before = {
        "discipline_level": record.discipline_level,
        "kpi": record.kpi,
        "absents": record.absents,
    }

    mapping = {"disciplineLevel": "discipline_level"}

    for key, value in payload.items():
        setattr(record, mapping.get(key, key), value)

    record.updated_by = current_user.full_name
    create_audit_log(
        db=db,
        action="UPDATE_DISCIPLINE_RECORD",
        resource_type="discipline",
        resource_id=record.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "discipline_level": record.discipline_level,
            "kpi": record.kpi,
            "absents": record.absents,
        },
    )
    db.commit()
    db.refresh(record)
    return api_response(data=_record_out(record))

