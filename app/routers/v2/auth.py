from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.rate_limit import rate_limiter
from app.core.redis import redis_client
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
from app.schemas_v2 import LoginResponseV2
from app.services.v2.auth_service import AuthServiceV2

router = APIRouter(prefix="/auth", tags=["auth-v2"])


@router.post("/login", response_model=LoginResponseV2, dependencies=[Depends(rate_limiter(max_requests=5, window_seconds=60))])
def login_v2(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    """v2 login endpoint — trả thêm `permissions` và `mfaRequired` để demo khác biệt"""
    service = AuthServiceV2(db)
    result = service.authenticate(username=body.username, password=body.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sai thong tin dang nhap"
        )

    # create audit and commit (service may have done side effects)
    user = db.get(User, result["user_id"]) if result.get("user_id") else None
    if user:
        create_audit_log(
            db=db,
            action="LOGIN_V2",
            resource_type="auth",
            resource_id=user.id,
            actor=user,
        )
        db.commit()

    return api_response(data=result)


@router.post("/refresh")
def refresh_v2(body: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    # v2 uses same refresh logic as v1 for now
    if redis_client.exists(f"blacklist:{body.refreshToken}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token khong hop le hoac da bi thu hoi",
        )

    payload = decode_token(body.refreshToken)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token khong hop le",
        )

    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Nguoi dung khong hop le"
        )

    exp = payload.get("exp")
    now = int(datetime.now(UTC).timestamp())
    ttl = exp - now
    if ttl > 0:
        redis_client.setex(f"blacklist:{body.refreshToken}", ttl, "revoked")

    return api_response(
        data={
            "accessToken": create_access_token(user.id),
            "refreshToken": create_refresh_token(user.id),
        }
    )
