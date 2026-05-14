import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.response import api_response
from app.db import get_db
from app.deps import get_current_user
from app.models import Meeting, Attendance, User, Member
from app.schemas import MeetingCreate, AttendanceListUpdate, MeetingUpdate
from app.utils import generate_prefixed_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _is_missing_relation_error(exc: Exception) -> bool:
    """Detect PostgreSQL undefined_table (SQLSTATE 42P01)."""
    current: Exception | None = exc
    while current is not None:
        if getattr(current, "pgcode", None) == "42P01":
            return True

        sqlstate = getattr(current, "sqlstate", None)
        if sqlstate == "42P01":
            return True

        current = getattr(current, "orig", None)

    return False

def _meeting_out(meeting: Meeting) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "date": meeting.date,
        "meetingType": meeting.meeting_type,
        "description": meeting.description,
        "status": meeting.status,
        "minutesUrl": meeting.minutes_url,
        "createdAt": getattr(meeting, "created_at", None),
        "updatedAt": getattr(meeting, "updated_at", None),
    }


@router.get("")
def list_meetings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    try:
        stmt = select(Meeting).order_by(Meeting.date.desc())
        rows = db.scalars(stmt).all()
        return api_response(data=[_meeting_out(row) for row in rows])
    except SQLAlchemyError as exc:
        if _is_missing_relation_error(exc):
            logger.warning("Meetings table is missing in database")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bảng dữ liệu meetings/attendances chưa tồn tại trên CSDL. Vui lòng chạy migration backend.",
            )
        logger.exception("Failed to list meetings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể truy xuất danh sách cuộc họp.",
        )


@router.post("")
def create_meeting(
    body: MeetingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
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
        minutes_url=body.minutesUrl,
    )

    try:
        db.add(meeting)
        db.flush()

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
    except SQLAlchemyError as exc:
        db.rollback()
        if _is_missing_relation_error(exc):
            logger.warning("Meetings table is missing in database")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bảng dữ liệu meetings/attendances chưa tồn tại trên CSDL. Vui lòng chạy migration backend.",
            )
        logger.exception("Failed to create meeting")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể khởi tạo cuộc họp.",
        )


@router.get("/{meeting_id}/attendance")
def get_attendance(
    meeting_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    try:
        meeting = db.get(Meeting, meeting_id)
        if not meeting:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy dữ liệu cuộc họp tương ứng."
            )
        
        attendances = db.scalars(
            select(Attendance).where(Attendance.meeting_id == meeting_id)
        ).all()
        
        return api_response(data=[{
            "id": a.id,
            "memberId": a.member_id,
            "status": a.status,
            "note": a.note,
        } for a in attendances])
    except SQLAlchemyError:
        logger.exception("Failed to get attendance for meeting %s", meeting_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lấy dữ liệu điểm danh.",
        )


@router.put("/{meeting_id}/attendance")
def update_attendance(
    meeting_id: str,
    body: AttendanceListUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.has_any_roles({"bcn", "bcm"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền cập nhật trạng thái điểm danh."
        )

    try:
        meeting = db.get(Meeting, meeting_id)
        if not meeting:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy dữ liệu cuộc họp tương ứng."
            )

        member_ids = {item.memberId for item in body.attendances}
        if member_ids:
            existing_member_ids = set(
                db.scalars(select(Member.id).where(Member.id.in_(member_ids))).all()
            )
            missing_member_ids = sorted(member_ids - existing_member_ids)
            if missing_member_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Có thành viên không tồn tại trong hệ thống.",
                        "missingMemberIds": missing_member_ids,
                    },
                )

        existing_attendances = db.scalars(
            select(Attendance).where(Attendance.meeting_id == meeting_id)
        ).all()
        for record in existing_attendances:
            db.delete(record)

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
    except IntegrityError:
        db.rollback()
        logger.exception("Attendance update integrity error for meeting_id=%s", meeting_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dữ liệu điểm danh không hợp lệ.",
        )
    except SQLAlchemyError as exc:
        db.rollback()
        if _is_missing_relation_error(exc):
            logger.warning("Meetings or attendances table is missing in database")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bảng dữ liệu meetings/attendances chưa tồn tại trên CSDL. Vui lòng chạy migration backend.",
            )
        logger.exception("Failed to update attendance for meeting_id=%s", meeting_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể cập nhật dữ liệu điểm danh.",
        )
@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    try:
        meeting = db.get(Meeting, meeting_id)
        if not meeting:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy dữ liệu cuộc họp tương ứng."
            )
        return api_response(data=_meeting_out(meeting))
    except SQLAlchemyError as exc:
        if _is_missing_relation_error(exc):
            logger.warning("Meetings table is missing in database")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bảng dữ liệu meetings/attendances chưa tồn tại trên CSDL. Vui lòng chạy migration backend.",
            )
    logger.exception("Failed to get meeting %s", meeting_id)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Không thể truy xuất dữ liệu cuộc họp.",
    )


@router.put("/{meeting_id}")
def update_meeting(
    meeting_id: str,
    body: MeetingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.has_any_roles({"bcn", "bcm"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền cập nhật dữ liệu cuộc họp."
        )

    try:
        meeting = db.get(Meeting, meeting_id)
        if not meeting:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy dữ liệu cuộc họp tương ứng."
            )

        # Cập nhật các trường nếu được cung cấp
        if body.title is not None:
            meeting.title = body.title
        if body.date is not None:
            meeting.date = body.date
        if body.meetingType is not None:
            meeting.meeting_type = body.meetingType
        if body.description is not None:
            meeting.description = body.description
        if body.status is not None:
            meeting.status = body.status
        if body.minutesUrl is not None:
            meeting.minutes_url = body.minutesUrl

        before_snapshot = {
            "title": meeting.title,
            "meetingType": meeting.meeting_type,
            "status": meeting.status,
            "minutesUrl": meeting.minutes_url,
        }

        create_audit_log(
            db=db,
            action="UPDATE_MEETING",
            resource_type="meeting",
            resource_id=meeting_id,
            actor=current_user,
            after_snapshot=before_snapshot,
        )

        db.commit()
        db.refresh(meeting)
        return api_response(data=_meeting_out(meeting))
    except SQLAlchemyError as exc:
        db.rollback()
        if _is_missing_relation_error(exc):
            logger.warning("Meetings table is missing in database")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bảng dữ liệu meetings/attendances chưa tồn tại trên CSDL. Vui lòng chạy migration backend.",
            )
        logger.exception("Failed to update meeting %s", meeting_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể cập nhật dữ liệu cuộc họp.",
        )