from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.rbac import require_roles
from app.core.response import api_response
from app.core.security import get_password_hash
from app.db import get_db
from app.models import User
from app.schemas import ResetPasswordRequest, UserCreate, UserStatusUpdate, UserUpdate
from app.utils import sanitize_pagination

router = APIRouter(prefix="/api/users", tags=["users"])


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.full_name,
        "role": user.role,
        "avatarInitials": user.avatar_initials,
        "email": user.email,
        "phone": user.phone,
        "isActive": user.is_active,
        "createdAt": user.created_at,
        "updatedAt": user.updated_at,
    }


@router.get("")
def list_users(
    search: str | None = None,
    role: str | None = None,
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("bcn")),
) -> dict:
    page, pageSize = sanitize_pagination(page, pageSize)

    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (User.username.ilike(pattern)) | (User.full_name.ilike(pattern))
        )
        count_stmt = count_stmt.where(
            (User.username.ilike(pattern)) | (User.full_name.ilike(pattern))
        )

    if role:
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)

    total = db.scalar(count_stmt) or 0
    users = db.scalars(stmt.offset((page - 1) * pageSize).limit(pageSize)).all()
    return api_response(
        data=[_user_out(u) for u in users],
        meta={"page": page, "pageSize": pageSize, "total": total},
    )


@router.post("")
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn")),
) -> dict:
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="username da ton tai"
        )

    user = User(
        username=body.username,
        password_hash=get_password_hash(body.password),
        full_name=body.fullName,
        role=body.role,
        avatar_initials=body.avatarInitials,
        email=body.email,
        phone=body.phone,
        is_active=True,
    )
    db.add(user)
    db.flush()
    create_audit_log(
        db=db,
        action="CREATE_USER",
        resource_type="user",
        resource_id=user.id,
        actor=current_user,
        after_snapshot={
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        },
    )
    db.commit()
    db.refresh(user)
    return api_response(data=_user_out(user))


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn")),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay user"
        )

    payload = body.model_dump(exclude_none=True)
    before = {
        "full_name": user.full_name,
        "role": user.role,
        "email": user.email,
    }

    mapping = {
        "fullName": "full_name",
        "avatarInitials": "avatar_initials",
    }

    for key, value in payload.items():
        setattr(user, mapping.get(key, key), value)

    create_audit_log(
        db=db,
        action="UPDATE_USER",
        resource_type="user",
        resource_id=user.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "full_name": user.full_name,
            "role": user.role,
            "email": user.email,
        },
    )
    db.commit()
    db.refresh(user)
    return api_response(data=_user_out(user))


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn")),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay user"
        )

    user.password_hash = get_password_hash(body.newPassword)
    create_audit_log(
        db=db,
        action="RESET_PASSWORD",
        resource_type="user",
        resource_id=user.id,
        actor=current_user,
    )
    db.commit()
    return api_response(data={"message": "Dat lai mat khau thanh cong"})


@router.patch("/{user_id}/status")
def update_status(
    user_id: str,
    body: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn")),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay user"
        )

    before = {"is_active": user.is_active}
    user.is_active = body.isActive
    create_audit_log(
        db=db,
        action="UPDATE_USER_STATUS",
        resource_type="user",
        resource_id=user.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={"is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    return api_response(data=_user_out(user))
