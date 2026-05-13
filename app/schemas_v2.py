from pydantic import BaseModel, Field


class UserOutV2(BaseModel):
    id: str
    username: str
    fullName: str
    role: str
    roles: list[str] = Field(default_factory=list)
    avatarInitials: str | None = None


class LoginResponseV2(BaseModel):
    accessToken: str
    refreshToken: str
    user: UserOutV2
    permissions: list[str]
    mfaRequired: bool = False
