from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.deps import get_current_user
from app.models import User


def require_roles(*roles: str) -> Callable:
    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ban khong co quyen thuc hien hanh dong nay",
            )
        return current_user

    return _dependency
