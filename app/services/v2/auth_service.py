from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_refresh_token, verify_password
from app.models import User


class AuthServiceV2:
    """Simple auth service for v2 demonstrating different response shape.

    For real projects, move more business logic here and keep routers thin.
    """

    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, username: str, password: str) -> dict | None:
        user = self.db.scalar(select(User).where(User.username == username))
        if not user or not verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            return None

        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)

        # v2 returns an expanded user object and permissions as an example
        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "fullName": user.full_name,
                "role": user.primary_role,
                "roles": user.role_names,
                "avatarInitials": user.avatar_initials,
            },
            "permissions": ["read:members", "write:requests"],
            "mfaRequired": False,
            "user_id": user.id,
        }
