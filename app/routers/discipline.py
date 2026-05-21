from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import config
from app.core.audit import create_audit_log
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import (
    Attendance,
    Competition,
    CompetitionResult,
    DisciplineRecord,
    Meeting,
    Member,
    User,
)
from app.schemas import DisciplineRecordCreate, DisciplineRecordUpdate
from app.utils import sanitize_pagination

router = APIRouter(prefix="/discipline-records", tags=["discipline"])


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
    warned_cases = (
        db.scalar(
            select(func.count())
            .select_from(DisciplineRecord)
            .where(DisciplineRecord.discipline_level != "Khong")
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

@router.post("/sync-attendance/{meeting_id}")
def sync_attendance_to_discipline(
    meeting_id: str,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Đồng bộ dữ liệu điểm danh từ một cuộc họp sang hồ sơ kỷ luật của thành viên.
    Quy trình:
    1. Lọc các thành viên có trạng thái "Absent" trong cuộc họp.
    2. Cộng dồn số buổi vắng vào DisciplineRecord.
    3. Tự động nội suy mức độ kỷ luật (discipline_level) dựa trên tổng số buổi vắng.
    """
    _ensure_legacy_mutation_allowed(response)

    # Kiểm tra phân quyền (RBAC) - Tránh việc thành viên tự ý kích hoạt đồng bộ
    if not current_user.has_any_roles({"bcn", "bvh_discipline"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền đồng bộ dữ liệu điểm danh",
        )

    # 1. Xác thực tính hợp lệ của cuộc họp
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy dữ liệu cuộc họp tương ứng",
        )

    # 2. Truy xuất danh sách vắng mặt không phép
    absent_records = db.scalars(
        select(Attendance).where(
            Attendance.meeting_id == meeting_id,
            Attendance.status == "Absent"
        )
    ).all()

    if not absent_records:
        return api_response(data={"message": "Không có thành viên vắng mặt không phép.", "syncedCount": 0})

    synced_count = 0
    for attendance in absent_records:
        member = db.get(Member, attendance.member_id)
        if not member:
            continue

        # 3. Tra cứu hoặc khởi tạo bản ghi kỷ luật hiện tại
        discipline_record = db.scalar(
            select(DisciplineRecord).where(DisciplineRecord.member_id == member.id)
        )

        before_snapshot = {}
        if discipline_record:
            # Lưu lại trạng thái trước khi thay đổi để ghi Audit Log
            before_snapshot = {
                "absents": discipline_record.absents,
                "discipline_level": discipline_record.discipline_level
            }
            discipline_record.absents += 1
        else:
            # Khởi tạo bản ghi mới với KPI tiêu chuẩn 100
            discipline_record = DisciplineRecord(
                member_id=member.id,
                mssv=member.mssv,
                name=member.name,
                committee=member.ban,
                absents=1,
                kpi=100.0,
                discipline_level="Không",
                updated_by=current_user.full_name
            )
            db.add(discipline_record)
            db.flush() # Đẩy vào session để lấy UUID sinh tự động

        # 4. Thuật toán phân cấp kỷ luật (Logic khoa học)
        # Hệ thống tự động ánh xạ số buổi vắng với hình thức kỷ luật
        if discipline_record.absents >= 3:
            discipline_record.discipline_level = "Cảnh cáo Lần 1"
        elif discipline_record.absents > 0:
            discipline_record.discipline_level = "Nhắc nhở"
        
        discipline_record.updated_by = current_user.full_name

        # 5. Ghi nhận nhật ký hệ thống (Audit Trail)
        create_audit_log(
            db=db,
            action="AUTO_SYNC_ABSENCE",
            resource_type="discipline",
            resource_id=discipline_record.id,
            actor=current_user,
            before_snapshot=before_snapshot if before_snapshot else None,
            after_snapshot={
                "absents": discipline_record.absents,
                "discipline_level": discipline_record.discipline_level,
                "meeting_id": meeting_id
            },
        )
        synced_count += 1
        
    # Xác nhận transaction vào cơ sở dữ liệu
    db.commit()

    return api_response(
        data={
            "message": f"Quá trình đồng bộ hoàn tất. Hệ thống đã cập nhật {synced_count} hồ sơ.",
            "syncedCount": synced_count
        }
    )

@router.post("/sync-competition-kpi/{competition_id}")
def sync_competition_to_kpi(
    competition_id: str,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Đồng bộ điểm thưởng (bonus_kpi) từ kết quả cuộc thi vào hồ sơ Kỷ luật & Hiệu suất.
    Hệ thống chỉ xử lý những bản ghi chưa được đồng bộ (is_synced == False).
    """
    _ensure_legacy_mutation_allowed(response)

    if not current_user.has_any_roles({"bcn", "bvh_discipline"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền cập nhật KPI hiệu suất.",
        )

    competition = db.get(Competition, competition_id)
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy dữ liệu cuộc thi.",
        )

    # Truy xuất các kết quả hợp lệ có điểm thưởng > 0 và chưa được đồng bộ
    unsynced_results = db.scalars(
        select(CompetitionResult).where(
            CompetitionResult.competition_id == competition_id,
            CompetitionResult.bonus_kpi > 0,
            CompetitionResult.is_synced.is_(False)
        )
    ).all()

    if not unsynced_results:
        return api_response(data={"message": "Không có điểm KPI mới nào cần đồng bộ.", "syncedCount": 0})

    synced_count = 0
    for result in unsynced_results:
        member = db.get(Member, result.member_id)
        if not member:
            continue

        discipline_record = db.scalar(
            select(DisciplineRecord).where(DisciplineRecord.member_id == member.id)
        )

        before_snapshot = {}
        if discipline_record:
            before_snapshot = {"kpi": discipline_record.kpi}
            # Cộng dồn điểm thưởng vào KPI hiện tại
            discipline_record.kpi += result.bonus_kpi
        else:
            # Nếu thành viên chưa có record, khởi tạo với mốc cơ bản 100 + điểm thưởng
            discipline_record = DisciplineRecord(
                member_id=member.id,
                mssv=member.mssv,
                name=member.name,
                committee=member.ban,
                absents=0,
                kpi=100.0 + result.bonus_kpi,
                discipline_level="Không",
                updated_by=current_user.full_name
            )
            db.add(discipline_record)
            db.flush()

        # Đánh dấu bản ghi này đã được đồng bộ thành công
        result.is_synced = True
        discipline_record.updated_by = current_user.full_name

        # Ghi Audit Log minh bạch lý do cộng điểm
        create_audit_log(
            db=db,
            action="AUTO_SYNC_COMPETITION_KPI",
            resource_type="discipline",
            resource_id=discipline_record.id,
            actor=current_user,
            before_snapshot=before_snapshot if before_snapshot else None,
            after_snapshot={
                "kpi": discipline_record.kpi,
                "reason": f"Cộng {result.bonus_kpi} điểm từ cuộc thi: {competition.title} ({result.achievement})"
            },
        )
        synced_count += 1

    db.commit()

    return api_response(
        data={
            "message": f"Đồng bộ hiệu suất thành công. Đã cập nhật KPI cho {synced_count} thành viên.",
            "syncedCount": synced_count
        }
    )
