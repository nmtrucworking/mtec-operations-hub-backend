from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field


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
    avatarInitials: str | None = None
    email: str | None = None
    phone: str | None = None
    isActive: bool


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    fullName: str
    role: str
    avatarInitials: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class UserUpdate(BaseModel):
    fullName: str | None = None
    role: str | None = None
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
    dob: date | None = None
    ban: str | None = None
    roleTitle: str | None = None
    status: str = "Active"
    phone: str | None = None
    email: EmailStr | None = None
    joinDate: date | None = None
    lop: str | None = None
    chuyenNganh: str | None = None
    khoa: str | None = None
    address: str | None = None
    experience: str | None = None
    goal: str | None = None
    orientation: str | None = None


class MemberUpdate(BaseModel):
    name: str | None = None
    gender: str | None = None
    dob: date | None = None
    ban: str | None = None
    roleTitle: str | None = None
    status: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    joinDate: date | None = None
    lop: str | None = None
    chuyenNganh: str | None = None
    khoa: str | None = None
    address: str | None = None
    experience: str | None = None
    goal: str | None = None
    orientation: str | None = None


class RequestCreate(BaseModel):
    mssv: str
    name: str
    type: str
    date: date
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
    date: date | None = None
    title: str
    type: str
    amount: float
    owner: str
    category: str


class TransactionUpdate(BaseModel):
    date: date | None = None
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
    disciplineLevel: str = "Khong"
    note: str | None = None


class DisciplineRecordUpdate(BaseModel):
    committee: str | None = None
    absents: int | None = Field(default=None, ge=0)
    kpi: float | None = Field(default=None, ge=0)
    disciplineLevel: str | None = None
    note: str | None = None


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


class AIGenerateInsightBody(BaseModel):
    prompt: str = Field(min_length=1)


class AIGenerateDraftBody(BaseModel):
    prompt: str = Field(min_length=1)
    context: str | None = None
