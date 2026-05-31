from __future__ import annotations

from datetime import date as dt_date
from datetime import datetime as dt_datetime

from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.discipline_levels import (
    DISCIPLINE_LEVEL_NONE,
    normalize_discipline_level,
)


ATTENDANCE_STATUSES = {"Present", "Absent", "Excused", "Unrecorded"}


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refreshToken: str


class UserOut(BaseModel):
    id: str
    username: str
    fullName: str
    role: str
    roles: list[str] = Field(default_factory=list)
    avatarInitials: str | None = None
    email: str | None = None
    phone: str | None = None
    isActive: bool


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    fullName: str
    role: str | None = None
    roles: list[str] | None = None
    avatarInitials: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class UserUpdate(BaseModel):
    fullName: str | None = None
    role: str | None = None
    roles: list[str] | None = None
    avatarInitials: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class UserStatusUpdate(BaseModel):
    isActive: bool


class ResetPasswordRequest(BaseModel):
    newPassword: str = Field(min_length=8)


class MemberCreate(BaseModel):
    mssv: str
    name: str
    gender: str | None = None
    dob: dt_date | None = None
    ban: str | None = None
    roleTitle: str | None = None
    status: str = "Active"
    phone: str | None = None
    email: EmailStr | None = None
    joinDate: dt_date | None = None
    lop: str | None = None
    chuyenNganh: str | None = None
    khoa: str | None = None
    address: str | None = None
    experience: str | None = None
    goal: str | None = None
    orientation: str | None = None
    hardSkills: List[MemberSkillIn] = Field(default_factory=list)
    softSkills: List[MemberSkillIn] = Field(default_factory=list)


class MemberSkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    level: str | None = None



class MemberUpdate(BaseModel):
    name: str | None = None
    gender: str | None = None
    dob: dt_date | None = None
    ban: str | None = None
    roleTitle: str | None = None
    status: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    joinDate: dt_date | None = None
    lop: str | None = None
    chuyenNganh: str | None = None
    khoa: str | None = None
    address: str | None = None
    experience: str | None = None
    goal: str | None = None
    orientation: str | None = None

    hardSkills: List[MemberSkillIn] | None = None
    softSkills: List[MemberSkillIn] | None = None


class RequestCreate(BaseModel):
    mssv: str
    name: str
    type: str
    date: dt_date
    reason: str
    financeDraftEnabled: bool = False
    financeDraftTitle: str | None = None
    financeDraftAmount: float | None = None
    financeDraftType: str | None = None
    financeDraftCategory: str | None = None


class RequestUpdate(BaseModel):
    reason: str | None = None
    financeDraftEnabled: bool | None = None
    financeDraftTitle: str | None = None
    financeDraftAmount: float | None = None
    financeDraftType: str | None = None
    financeDraftCategory: str | None = None


class ReviewRequestBody(BaseModel):
    status: str
    reviewNote: str | None = None


class TransactionCreate(BaseModel):
    date: dt_date | None = None
    title: str
    type: str
    amount: float
    owner: str
    category: str


class TransactionUpdate(BaseModel):
    date: dt_date | None = None
    title: str | None = None
    amount: float | None = None
    owner: str | None = None
    category: str | None = None


class ReviewTransactionBody(BaseModel):
    status: str
    reviewNote: str | None = None


class AssetCreate(BaseModel):
    name: str
    quantity: int = Field(ge=0)
    status: str
    holder: str | None = None
    category: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    status: str | None = None
    holder: str | None = None
    category: str | None = None


class DisciplineRecordCreate(BaseModel):
    memberId: str | None = None
    mssv: str
    name: str
    committee: str | None = None
    absents: int = Field(default=0, ge=0)
    kpi: float = Field(default=0, ge=0)
    disciplineLevel: str = DISCIPLINE_LEVEL_NONE
    note: str | None = None

    @field_validator("disciplineLevel")
    @classmethod
    def validate_discipline_level(cls, value: str) -> str:
        return normalize_discipline_level(value)


class DisciplineRecordUpdate(BaseModel):
    committee: str | None = None
    absents: int | None = Field(default=None, ge=0)
    kpi: float | None = Field(default=None, ge=0)
    disciplineLevel: str | None = None
    note: str | None = None

    @field_validator("disciplineLevel")
    @classmethod
    def validate_discipline_level(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_discipline_level(value)


class SettingsProfileUpdate(BaseModel):
    fullName: str | None = None
    avatarInitials: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class ChangePasswordBody(BaseModel):
    currentPassword: str
    newPassword: str = Field(min_length=8)


class NotificationSettingsUpdate(BaseModel):
    noti1: bool | None = None
    noti2: bool | None = None
    noti3: bool | None = None
    noti4: bool | None = None
    emailNotifications: bool | None = None
    pushNotifications: bool | None = None
    smsNotifications: bool | None = None
    financeNotifications: bool | None = None


class CompetitionCreate(BaseModel):
    title: str
    date: dt_date
    scale: str
    status: Optional[str] = "Ongoing"

class CompetitionResultCreate(BaseModel):
    memberId: str
    achievement: str
    bonusKpi: float

class MeetingCreate(BaseModel):
    title: str
    date: dt_datetime
    meetingType: str
    description: Optional[str] = None
    status: Optional[str] = "Scheduled"
    minutesUrl: Optional[str] = None

class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    date: Optional[dt_datetime] = None
    meetingType: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    minutesUrl: Optional[str] = None

class AttendanceUpdateItem(BaseModel):
    memberId: str
    status: str
    note: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ATTENDANCE_STATUSES:
            raise ValueError(
                "Attendance status must be Present, Absent, Excused, or Unrecorded"
            )
        return value

class AttendanceListUpdate(BaseModel):
    attendances: List[AttendanceUpdateItem]
