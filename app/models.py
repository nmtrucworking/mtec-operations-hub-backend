from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# Utility function to generate UUIDs for primary keys
def _uuid() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), index=True)
    avatar_initials: Mapped[str | None] = mapped_column(String(10), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC)
    )
    user_roles: Mapped[list[UserRole]] = relationship(
        "UserRole", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def role_names(self) -> list[str]:
        role_names = [user_role.role.name for user_role in self.user_roles if user_role.role]
        if role_names:
            return sorted(set(role_names))
        return [self.role] if self.role else []

    @property
    def primary_role(self) -> str:
        priorities = {
            "bcn": 0,
            "bvh_finance": 1,
            "bvh_hr": 2,
            "bvh_discipline": 3,
            "bvh_logistics": 4,
            "bcm": 5,
            "member": 6,
        }
        role_names = self.role_names
        if not role_names:
            return "member"
        return min(role_names, key=lambda item: priorities.get(item, 999))

    def has_role(self, role: str) -> bool:
        return role in self.role_names

    def has_any_roles(self, roles: set[str] | list[str] | tuple[str, ...]) -> bool:
        if not roles:
            return False
        role_set = set(self.role_names)
        return bool(role_set.intersection(set(roles)))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    user_roles: Mapped[list[UserRole]] = relationship(
        "UserRole", back_populates="role", cascade="all, delete-orphan"
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(UTC))

    user: Mapped[User] = relationship("User", back_populates="user_roles")
    role: Mapped[Role] = relationship("Role", back_populates="user_roles")


class Member(Base):
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mssv: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    ban: Mapped[str | None] = mapped_column(String(50), nullable=True)
    role_title: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Active")
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    join_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lop: Mapped[str | None] = mapped_column(String(50), nullable=True)
    chuyen_nganh: Mapped[str | None] = mapped_column(String(120), nullable=True)
    khoa: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    orientation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC)
    )


class MemberSkill(Base):
    __tablename__ = "member_skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    member_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("members.id"), index=True
    )
    type: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(80))
    level: Mapped[str] = mapped_column(String(20))


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mssv: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(60), index=True)
    date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="Cho duyet", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_transaction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    finance_draft_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    finance_draft_title: Mapped[str | None] = mapped_column(String(180), nullable=True)
    finance_draft_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    finance_draft_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    finance_draft_category: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC)
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    date: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    type: Mapped[str] = mapped_column(String(10), index=True)
    amount: Mapped[float] = mapped_column(Float)
    owner: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    required_approval_role: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("requests.id"), nullable=True
    )
    linked_request_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC)
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)
    holder: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC)
    )


class DisciplineRecord(Base):
    __tablename__ = "discipline_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    member_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("members.id"), nullable=True
    )
    mssv: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120))
    committee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    absents: Mapped[int] = mapped_column(Integer, default=0)
    kpi: Mapped[float] = mapped_column(Float, default=0)
    discipline_level: Mapped[str] = mapped_column(String(40), default="Khong")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC)
    )


class SettingsNotification(Base):
    __tablename__ = "settings_notifications"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), primary_key=True
    )
    noti1: Mapped[bool] = mapped_column(Boolean, default=True)
    noti2: Mapped[bool] = mapped_column(Boolean, default=True)
    noti3: Mapped[bool] = mapped_column(Boolean, default=True)
    noti4: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC)
    )


class AIGenerationLog(Base):
    __tablename__ = "ai_generation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    module: Mapped[str] = mapped_column(String(30))
    prompt: Mapped[str] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(30), default="gemini")
    status: Mapped[str] = mapped_column(String(20), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(UTC))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(60), index=True)
    resource_type: Mapped[str] = mapped_column(String(40), index=True)
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    before_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(UTC))
