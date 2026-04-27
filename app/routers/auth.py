from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import api_response
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginRequest, RefreshRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.full_name,
        "role": user.role,
        "avatarInitials": user.avatar_initials,
    }


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sai thong tin dang nhap")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tai khoan da bi khoa")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return api_response(
        data={
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": _user_payload(user),
        }
    )


@router.post("/logout")
def logout() -> dict:
    return api_response(data={"message": "Da dang xuat"})


@router.get("/me")
def me(current_user: User = Depends(get_current_user)) -> dict:
    return api_response(data=_user_payload(current_user))


@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    payload = decode_token(body.refreshToken)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token khong hop le")

    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nguoi dung khong hop le")

    return api_response(
        data={
            "accessToken": create_access_token(user.id),
            "refreshToken": create_refresh_token(user.id),
        }
    )
