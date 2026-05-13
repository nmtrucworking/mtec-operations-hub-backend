from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import Meeting, Attendance, User
from app.schemas import MeetingCreate, AttendanceListUpdate
from app.utils import generate_prefixed_id

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _meeting_out(meeting: Meeting) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "date": meeting.date,
        "meetingType": meeting.meeting_type,
        "description": meeting.description,
        "status": meeting.status,
        "createdAt": getattr(meeting, "created_at", None),
        "updatedAt": getattr(meeting, "updated_at", None),
    }


@router.get("")
def list_meetings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """
    Truy xuất danh sách toàn bộ cuộc họp trong hệ thống.
    Dữ liệu được sắp xếp theo thời gian giảm dần nhằm ưu tiên hiển thị các sự kiện mới nhất.
    """
    stmt = select(Meeting).order_by(Meeting.date.desc())
    rows = db.scalars(stmt).all()
    return api_response(data=[_meeting_out(row) for row in rows])


@router.post("")
def create_meeting(
    body: MeetingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Khởi tạo một bản ghi cuộc họp mới.
    Quyền truy cập: Chỉ cho phép các tài khoản thuộc Ban Chủ nhiệm (bcn) hoặc Ban Chuyên môn (bcm).
    """
    if not current_user.has_any_roles({"bcn", "bcm"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền khởi tạo dữ liệu cuộc họp."
        )

    meeting = Meeting(
        id=generate_prefixed_id("MEET"),
        title=body.title,
        date=body.date,
        meeting_type=body.meetingType,
        description=body.description,
        status=body.status or "Scheduled",
    )
    db.add(meeting)
    db.flush()

    # Lưu vết thao tác khởi tạo
    create_audit_log(
        db=db,
        action="CREATE_MEETING",
        resource_type="meeting",
        resource_id=meeting.id,
        actor=current_user,
        after_snapshot={
            "title": meeting.title,
            "meetingType": meeting.meeting_type,
            "status": meeting.status
        },
    )
    db.commit()
    db.refresh(meeting)
    return api_response(data=_meeting_out(meeting))


@router.put("/{meeting_id}/attendance")
def update_attendance(
    meeting_id: str,
    body: AttendanceListUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Cập nhật danh sách điểm danh cho một cuộc họp.
    Cơ chế hoạt động (Idempotency): Xóa toàn bộ bản ghi điểm danh cũ của cuộc họp này và chèn danh sách mới. 
    Điều này đảm bảo tính nhất quán của dữ liệu khi client gửi lại request nhiều lần.
    """
    if not current_user.has_any_roles({"bcn", "bcm"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền cập nhật trạng thái điểm danh."
        )

    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy dữ liệu cuộc họp tương ứng."
        )

    # Truy xuất và loại bỏ dữ liệu điểm danh hiện tại của cuộc họp
    existing_attendances = db.scalars(
        select(Attendance).where(Attendance.meeting_id == meeting_id)
    ).all()
    for record in existing_attendances:
        db.delete(record)

    # Khởi tạo danh sách điểm danh mới từ payload
    new_records_count = 0
    for item in body.attendances:
        attendance_record = Attendance(
            meeting_id=meeting_id,
            member_id=item.memberId,
            status=item.status,
            note=item.note
        )
        db.add(attendance_record)
        new_records_count += 1

    # Lưu vết thao tác cập nhật
    create_audit_log(
        db=db,
        action="UPDATE_ATTENDANCE",
        resource_type="meeting",
        resource_id=meeting_id,
        actor=current_user,
        after_snapshot={"details": f"Cập nhật danh sách điểm danh cho {new_records_count} thành viên."}
    )
    
    db.commit()
    return api_response(data={"message": "Cập nhật dữ liệu điểm danh thành công", "count": new_records_count})