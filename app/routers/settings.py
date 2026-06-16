from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.response import api_response
from app.core.security import get_password_hash, verify_password
from app.db import get_db
from app.deps import get_current_user
from app.models import SettingsNotification, User
from app.schemas import (
    ChangePasswordBody,
    NotificationSettingsUpdate,
    SettingsProfileUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "avatars"
ALLOWED_AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_AVATAR_SIZE_BYTES = 2 * 1024 * 1024


def _user_profile_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.full_name,
        "role": user.primary_role,
        "roles": user.role_names,
        "avatarInitials": user.avatar_initials,
        "avatarUrl": user.avatar_url,
        "avatarSource": user.avatar_source,
        "email": user.email,
        "phone": user.phone,
    }


@router.get("/profile")
def get_profile(current_user: User = Depends(get_current_user)) -> dict:
    return api_response(data=_user_profile_payload(current_user))


@router.patch("/profile")
def update_profile(
    body: SettingsProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    payload = body.model_dump(exclude_none=True)
    before = {
        "full_name": current_user.full_name,
        "avatar_initials": current_user.avatar_initials,
        "avatar_url": current_user.avatar_url,
        "avatar_source": current_user.avatar_source,
        "email": current_user.email,
        "phone": current_user.phone,
    }

    mapping = {
        "fullName": "full_name",
        "avatarInitials": "avatar_initials",
        "avatarUrl": "avatar_url",
        "avatarSource": "avatar_source",
    }

    for key, value in payload.items():
        setattr(current_user, mapping.get(key, key), value)

    create_audit_log(
        db=db,
        action="UPDATE_PROFILE",
        resource_type="settings",
        resource_id=current_user.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "full_name": current_user.full_name,
            "avatar_initials": current_user.avatar_initials,
            "avatar_url": current_user.avatar_url,
            "avatar_source": current_user.avatar_source,
            "email": current_user.email,
            "phone": current_user.phone,
        },
    )
    db.commit()
    db.refresh(current_user)
    return api_response(data=_user_profile_payload(current_user))


@router.post("/avatar/upload")
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    content_type = (file.content_type or "").lower()
    ext = ALLOWED_AVATAR_TYPES.get(content_type)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chi ho tro JPG, PNG hoac WEBP",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File avatar rong",
        )
    if len(content) > MAX_AVATAR_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar vuot qua gioi han 2MB",
        )

    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    filename = f"{current_user.id}-{uuid4().hex}{ext}"
    file_path = UPLOAD_ROOT / filename
    file_path.write_bytes(content)

    before = {
        "avatar_url": current_user.avatar_url,
        "avatar_source": current_user.avatar_source,
    }
    current_user.avatar_url = f"/uploads/avatars/{filename}"
    current_user.avatar_source = "device"

    create_audit_log(
        db=db,
        action="UPLOAD_AVATAR",
        resource_type="settings",
        resource_id=current_user.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "avatar_url": current_user.avatar_url,
            "avatar_source": current_user.avatar_source,
        },
    )
    db.commit()
    db.refresh(current_user)
    return api_response(data=_user_profile_payload(current_user))


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not verify_password(body.currentPassword, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mat khau hien tai khong dung",
        )

    if body.currentPassword == body.newPassword:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mat khau moi khong duoc trung",
        )

    current_user.password_hash = get_password_hash(body.newPassword)
    create_audit_log(
        db=db,
        action="CHANGE_PASSWORD",
        resource_type="settings",
        resource_id=current_user.id,
        actor=current_user,
    )
    db.commit()
    return api_response(data={"message": "Doi mat khau thanh cong"})


def _ensure_notification_row(db: Session, user_id: str) -> SettingsNotification:
    row = db.get(SettingsNotification, user_id)
    if row:
        if row.noti1 or row.noti3:
            row.noti1 = False
            row.noti3 = False
            db.commit()
            db.refresh(row)
        return row

    row = SettingsNotification(
        user_id=user_id, noti1=False, noti2=False, noti3=False, noti4=True
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/notifications")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    row = _ensure_notification_row(db, current_user.id)
    return api_response(
        data={
            "userId": row.user_id,
            "noti1": False,
            "noti2": row.noti2,
            "noti3": False,
            "noti4": row.noti4,
            "emailNotifications": False,
            "pushNotifications": row.noti2,
            "smsNotifications": False,
            "financeNotifications": row.noti4,
            "lockedChannels": ["email", "sms"],
            "updatedAt": row.updated_at,
        }
    )


@router.patch("/notifications")
def update_notifications(
    body: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    row = _ensure_notification_row(db, current_user.id)
    payload = body.model_dump(exclude_none=True)

    mapping = {
        "pushNotifications": "noti2",
        "financeNotifications": "noti4",
        "noti2": "noti2",
        "noti4": "noti4",
    }

    for key, value in payload.items():
        target = mapping.get(key)
        if target:
            setattr(row, target, value)

    row.noti1 = False
    row.noti3 = False

    db.commit()
    db.refresh(row)
    return api_response(
        data={
            "userId": row.user_id,
            "noti1": False,
            "noti2": row.noti2,
            "noti3": False,
            "noti4": row.noti4,
            "emailNotifications": False,
            "pushNotifications": row.noti2,
            "smsNotifications": False,
            "financeNotifications": row.noti4,
            "lockedChannels": ["email", "sms"],
            "updatedAt": row.updated_at,
        }
    )
