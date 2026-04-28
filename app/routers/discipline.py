from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import DisciplineRecord, User
from app.schemas import DisciplineRecordCreate, DisciplineRecordUpdate
from app.utils import sanitize_pagination

router = APIRouter(prefix="/api/discipline-records", tags=["discipline"])


def _record_out(record: DisciplineRecord) -> dict:
    return {
        "id": record.id,
        "memberId": record.member_id,
        "mssv": record.mssv,
        "name": record.name,
        "committee": record.committee,
        "absents": record.absents,
        "kpi": record.kpi,
        "disciplineLevel": record.discipline_level,
        "note": record.note,
        "updatedBy": record.updated_by,
        "updatedAt": record.updated_at,
    }


@router.get("")
def list_records(
    search: str | None = None,
    disciplineLevel: str | None = None,
    committee: str | None = None,
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
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
        stmt = stmt.where(DisciplineRecord.discipline_level == disciplineLevel)
        count_stmt = count_stmt.where(
            DisciplineRecord.discipline_level == disciplineLevel
        )

    if committee:
        stmt = stmt.where(DisciplineRecord.committee == committee)
        count_stmt = count_stmt.where(DisciplineRecord.committee == committee)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.offset((page - 1) * pageSize).limit(pageSize)).all()
    return api_response(
        data=[_record_out(row) for row in rows],
        meta={"page": page, "pageSize": pageSize, "total": total},
    )


@router.post("")
def create_record(
    body: DisciplineRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.role not in {"bcn", "bvh_discipline"}:
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
    db.commit()
    db.refresh(record)
    return api_response(data=_record_out(record))


@router.patch("/{record_id}")
def update_record(
    record_id: str,
    body: DisciplineRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.role not in {"bcn", "bvh_discipline"}:
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
    mapping = {"disciplineLevel": "discipline_level"}

    for key, value in payload.items():
        setattr(record, mapping.get(key, key), value)

    record.updated_by = current_user.full_name
    db.commit()
    db.refresh(record)
    return api_response(data=_record_out(record))
