from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# Utility function to generate UUIDs for primary keys
def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    # add relationship to attendance records
    attendances: Mapped[list[Attendance]] = relationship("Attendance", back_populates="member")
    skills: Mapped[list["MemberSkill"]] = relationship(
        "MemberSkill", back_populates="member", cascade="all, delete-orphan"
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
    member: Mapped[Member] = relationship("Member", back_populates="skills")


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
    discipline_level: Mapped[str] = mapped_column(String(40), default="NONE")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC)
    )


class DisciplineAttendanceSyncLog(Base):
    __tablename__ = "discipline_attendance_sync_logs"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id",
            "member_id",
            name="uq_discipline_attendance_sync_logs_meeting_member",
        ),
        Index("ix_discipline_attendance_sync_logs_meeting_id", "meeting_id"),
        Index("ix_discipline_attendance_sync_logs_member_id", "member_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(String(36), ForeignKey("meetings.id"))
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"))
    discipline_record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("discipline_records.id"), nullable=True
    )
    synced_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EvaluationCycle(Base):
    __tablename__ = "evaluation_cycles"
    __table_args__ = (
        UniqueConstraint("code", name="uq_evaluation_cycles_code"),
        Index("ix_evaluation_cycles_status", "status"),
        Index("ix_evaluation_cycles_type", "type"),
        Index("ix_evaluation_cycles_start_date", "start_date"),
        Index("ix_evaluation_cycles_end_date", "end_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(180))
    type: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    approved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class EvaluationCriterion(Base):
    __tablename__ = "evaluation_criteria"
    __table_args__ = (
        UniqueConstraint(
            "code",
            "unit_code",
            "effective_from",
            name="uq_evaluation_criteria_code_unit_effective",
        ),
        Index("ix_evaluation_criteria_component", "component"),
        Index("ix_evaluation_criteria_unit_code", "unit_code"),
        Index("ix_evaluation_criteria_is_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    component: Mapped[str] = mapped_column(String(20))
    unit_scope: Mapped[str] = mapped_column(String(30))
    unit_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    max_score: Mapped[float] = mapped_column(Float)
    score_method: Mapped[str] = mapped_column(String(30))
    requires_evidence: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class MemberCycleRole(Base):
    __tablename__ = "member_cycle_roles"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id", "member_id", "unit_code", name="uq_member_cycle_roles_cycle_member_unit"
        ),
        Index("ix_member_cycle_roles_cycle_id", "cycle_id"),
        Index("ix_member_cycle_roles_member_id", "member_id"),
        Index("ix_member_cycle_roles_unit_code", "unit_code"),
        Index("ix_member_cycle_roles_role_type", "role_type"),
        Index("ix_member_cycle_roles_is_primary", "is_primary"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cycle_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_cycles.id"))
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"))
    unit_code: Mapped[str] = mapped_column(String(30))
    role_type: Mapped[str] = mapped_column(String(30))
    role_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    participation_weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    approved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class EvaluationScoreEvent(Base):
    __tablename__ = "evaluation_score_events"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id",
            "member_id",
            "criterion_code",
            "source_type",
            "source_id",
            "event_type",
            name="uq_evaluation_score_events_source_dedupe",
        ),
        Index("ix_evaluation_score_events_cycle_id", "cycle_id"),
        Index("ix_evaluation_score_events_member_id", "member_id"),
        Index("ix_evaluation_score_events_criterion_id", "criterion_id"),
        Index("ix_evaluation_score_events_criterion_code", "criterion_code"),
        Index("ix_evaluation_score_events_component", "component"),
        Index("ix_evaluation_score_events_unit_code", "unit_code"),
        Index("ix_evaluation_score_events_event_type", "event_type"),
        Index("ix_evaluation_score_events_source_type", "source_type"),
        Index("ix_evaluation_score_events_source_id", "source_id"),
        Index("ix_evaluation_score_events_is_void", "is_void"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cycle_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_cycles.id"))
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"))
    criterion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_criteria.id")
    )
    criterion_code: Mapped[str] = mapped_column(String(50))
    component: Mapped[str] = mapped_column(String(20))
    unit_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    event_type: Mapped[str] = mapped_column(String(30))
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    raw_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_delta: Mapped[float] = mapped_column(Float, default=0.0)
    max_score_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    is_void: Mapped[bool] = mapped_column(Boolean, default=False)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class EvaluationEvidence(Base):
    __tablename__ = "evaluation_evidence"
    __table_args__ = (
        Index("ix_evaluation_evidence_cycle_id", "cycle_id"),
        Index("ix_evaluation_evidence_member_id", "member_id"),
        Index("ix_evaluation_evidence_criterion_id", "criterion_id"),
        Index("ix_evaluation_evidence_score_event_id", "score_event_id"),
        Index("ix_evaluation_evidence_evidence_type", "evidence_type"),
        Index("ix_evaluation_evidence_status", "status"),
        UniqueConstraint("score_event_id", name="uq_evaluation_evidence_score_event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cycle_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_cycles.id"))
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"))
    criterion_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluation_criteria.id"), nullable=True
    )
    score_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluation_score_events.id"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    verified_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class MemberEvaluation(Base):
    __tablename__ = "member_evaluations"
    __table_args__ = (
        UniqueConstraint("cycle_id", "member_id", name="uq_member_evaluations_cycle_member"),
        Index("ix_member_evaluations_cycle_id", "cycle_id"),
        Index("ix_member_evaluations_member_id", "member_id"),
        Index("ix_member_evaluations_status", "status"),
        Index("ix_member_evaluations_final_classification", "final_classification"),
        Index("ix_member_evaluations_total_score", "total_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cycle_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_cycles.id"))
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"))
    component_i_score: Mapped[float] = mapped_column(Float, default=0.0)
    component_ii_score: Mapped[float] = mapped_column(Float, default=0.0)
    component_iii_a_score: Mapped[float] = mapped_column(Float, default=0.0)
    component_iii_b_score: Mapped[float] = mapped_column(Float, default=0.0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    preliminary_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    final_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    attendance_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    blockers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculation_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class MemberEvaluationBreakdown(Base):
    __tablename__ = "member_evaluation_breakdowns"
    __table_args__ = (
        UniqueConstraint(
            "member_evaluation_id",
            "criterion_code",
            "unit_code",
            name="uq_member_evaluation_breakdowns_eval_criterion_unit",
        ),
        Index("ix_member_evaluation_breakdowns_cycle_id", "cycle_id"),
        Index("ix_member_evaluation_breakdowns_member_id", "member_id"),
        Index("ix_member_evaluation_breakdowns_criterion_id", "criterion_id"),
        Index("ix_member_evaluation_breakdowns_criterion_code", "criterion_code"),
        Index("ix_member_evaluation_breakdowns_component", "component"),
        Index("ix_member_evaluation_breakdowns_unit_code", "unit_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    member_evaluation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("member_evaluations.id")
    )
    cycle_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_cycles.id"))
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"))
    criterion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_criteria.id")
    )
    criterion_code: Mapped[str] = mapped_column(String(50))
    component: Mapped[str] = mapped_column(String(20))
    unit_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    raw_score: Mapped[float] = mapped_column(Float)
    final_score: Mapped[float] = mapped_column(Float)
    max_score_snapshot: Mapped[float] = mapped_column(Float)
    cap_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    calculation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class EvaluationAppeal(Base):
    __tablename__ = "evaluation_appeals"
    __table_args__ = (
        Index("ix_evaluation_appeals_cycle_id", "cycle_id"),
        Index("ix_evaluation_appeals_member_id", "member_id"),
        Index("ix_evaluation_appeals_member_evaluation_id", "member_evaluation_id"),
        Index("ix_evaluation_appeals_criterion_id", "criterion_id"),
        Index("ix_evaluation_appeals_status", "status"),
        Index("ix_evaluation_appeals_appeal_type", "appeal_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cycle_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_cycles.id"))
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"))
    member_evaluation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("member_evaluations.id"), nullable=True
    )
    criterion_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluation_criteria.id"), nullable=True
    )
    criterion_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    appeal_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    requested_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    resolved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class DisciplineCase(Base):
    __tablename__ = "discipline_cases"
    __table_args__ = (
        UniqueConstraint("case_code", name="uq_discipline_cases_case_code"),
        Index("ix_discipline_cases_cycle_id", "cycle_id"),
        Index("ix_discipline_cases_member_id", "member_id"),
        Index("ix_discipline_cases_case_type", "case_type"),
        Index("ix_discipline_cases_severity", "severity"),
        Index("ix_discipline_cases_status", "status"),
        Index("ix_discipline_cases_blocker_code", "blocker_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cycle_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluation_cycles.id"), nullable=True
    )
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"))
    case_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    case_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocker_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    point_impact: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    resolved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
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

class Meeting(Base):
    """
    Model lưu trữ thông tin các cuộc họp hoặc hoạt động tập trung của CLB.
    Dùng làm căn cứ để thực hiện điểm danh.
    """
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), index=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    meeting_type: Mapped[str] = mapped_column(String(50), index=True) # VD: 'Họp định kỳ', 'Họp Ban'
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Scheduled") # Scheduled, Completed, Cancelled
    minutes_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # URL biên bản từ Google Drive
    
    # Quan hệ với bảng điểm danh
    attendances: Mapped[list[Attendance]] = relationship(
        "Attendance", back_populates="meeting", cascade="all, delete-orphan"
    )

class Attendance(Base):
    """
    Bảng chi tiết điểm danh thành viên cho từng cuộc họp.
    Dữ liệu từ bảng này sẽ được dùng để tự động cập nhật kỷ luật chuyên cần.
    """
    __tablename__ = "attendances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id"), index=True
    )
    member_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("members.id"), index=True
    )
    # Trạng thái: Present, Absent, Excused, Unrecorded.
    status: Mapped[str] = mapped_column(String(20), default="Unrecorded")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    # Định nghĩa quan hệ ngược lại
    meeting: Mapped[Meeting] = relationship("Meeting", back_populates="attendances")
    member: Mapped[Member] = relationship("Member")

class Competition(Base):
    """
    Model lưu trữ thông tin các cuộc thi, sự kiện học thuật hoặc phong trào.
    """
    __tablename__ = "competitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), index=True)
    date: Mapped[date] = mapped_column(Date)
    scale: Mapped[str] = mapped_column(String(50))  # Cấp CLB, Cấp Khoa, Cấp Trường, Quốc gia
    status: Mapped[str] = mapped_column(String(20), default="Ongoing") # Ongoing, Completed
    
    # Quan hệ với bảng kết quả
    results: Mapped[list["CompetitionResult"]] = relationship(
        "CompetitionResult", back_populates="competition", cascade="all, delete-orphan"
    )

class CompetitionResult(Base):
    """
    Bảng lưu trữ kết quả tham gia và mức điểm KPI thưởng tương ứng của thành viên.
    """
    __tablename__ = "competition_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("competitions.id"), index=True
    )
    member_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("members.id"), index=True
    )
    achievement: Mapped[str] = mapped_column(String(100)) # VD: 'Giải Nhất', 'Top 5', 'Tham gia'
    bonus_kpi: Mapped[float] = mapped_column(Float, default=0.0) # Điểm hiệu suất được cộng
    is_synced: Mapped[bool] = mapped_column(Boolean, default=False) # Cờ đánh dấu đã đồng bộ KPI chưa
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    competition: Mapped[Competition] = relationship("Competition", back_populates="results")
    member: Mapped[Member] = relationship("Member")
