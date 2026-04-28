from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/profile")
def get_profile(current_user: User = Depends(get_current_user)) -> dict:
    return api_response(
        data={
            "id": current_user.id,
            "username": current_user.username,
            "fullName": current_user.full_name,
            "role": current_user.role,
            "avatarInitials": current_user.avatar_initials,
            "email": current_user.email,
            "phone": current_user.phone,
        }
    )


@router.patch("/profile")
def update_profile(
    body: SettingsProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    payload = body.model_dump(exclude_none=True)
    mapping = {
        "fullName": "full_name",
        "avatarInitials": "avatar_initials",
    }

    for key, value in payload.items():
        setattr(current_user, mapping.get(key, key), value)

    db.commit()
    db.refresh(current_user)
    return api_response(
        data={
            "id": current_user.id,
            "username": current_user.username,
            "fullName": current_user.full_name,
            "role": current_user.role,
            "avatarInitials": current_user.avatar_initials,
            "email": current_user.email,
            "phone": current_user.phone,
        }
    )


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
    db.commit()
    return api_response(data={"message": "Doi mat khau thanh cong"})


def _ensure_notification_row(db: Session, user_id: str) -> SettingsNotification:
    row = db.get(SettingsNotification, user_id)
    if row:
        return row

    row = SettingsNotification(
        user_id=user_id, noti1=True, noti2=True, noti3=True, noti4=True
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
            "noti1": row.noti1,
            "noti2": row.noti2,
            "noti3": row.noti3,
            "noti4": row.noti4,
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

    for key, value in payload.items():
        setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return api_response(
        data={
            "userId": row.user_id,
            "noti1": row.noti1,
            "noti2": row.noti2,
            "noti3": row.noti3,
            "noti4": row.noti4,
            "updatedAt": row.updated_at,
        }
    )
