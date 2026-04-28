from datetime import date
from typing import Optional

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
    avatarInitials: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    isActive: bool


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    fullName: str
    role: str
    avatarInitials: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


class UserUpdate(BaseModel):
    fullName: Optional[str] = None
    role: Optional[str] = None
    avatarInitials: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


class UserStatusUpdate(BaseModel):
    isActive: bool


class ResetPasswordRequest(BaseModel):
    newPassword: str = Field(min_length=8)


class MemberCreate(BaseModel):
    mssv: str
    name: str
    gender: Optional[str] = None
    dob: date | None = None
    ban: Optional[str] = None
    roleTitle: Optional[str] = None
    status: str = "Active"
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    joinDate: date | None = None
    lop: Optional[str] = None
    chuyenNganh: Optional[str] = None
    khoa: Optional[str] = None
    address: Optional[str] = None
    experience: Optional[str] = None
    goal: Optional[str] = None
    orientation: Optional[str] = None


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    dob: date | None = None
    ban: Optional[str] = None
    roleTitle: Optional[str] = None
    status: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    joinDate: date | None = None
    lop: Optional[str] = None
    chuyenNganh: Optional[str] = None
    khoa: Optional[str] = None
    address: Optional[str] = None
    experience: Optional[str] = None
    goal: Optional[str] = None
    orientation: Optional[str] = None


class RequestCreate(BaseModel):
    mssv: str
    name: str
    type: str
    date: date
    reason: str
    financeDraftEnabled: bool = False
    financeDraftTitle: Optional[str] = None
    financeDraftAmount: float | None = None
    financeDraftType: Optional[str] = None
    financeDraftCategory: Optional[str] = None


class RequestUpdate(BaseModel):
    reason: Optional[str] = None
    financeDraftEnabled: bool | None = None
    financeDraftTitle: Optional[str] = None
    financeDraftAmount: float | None = None
    financeDraftType: Optional[str] = None
    financeDraftCategory: Optional[str] = None


class ReviewRequestBody(BaseModel):
    status: str
    reviewNote: Optional[str] = None


class TransactionCreate(BaseModel):
    date: Optional[date] = None
    title: str
    type: str
    amount: float
    owner: str
    category: str


class TransactionUpdate(BaseModel):
    date: Optional[date] = None
    title: Optional[str] = None
    amount: float | None = None
    owner: Optional[str] = None
    category: Optional[str] = None


class ReviewTransactionBody(BaseModel):
    status: str
    reviewNote: Optional[str] = None


class AssetCreate(BaseModel):
    name: str
    quantity: int = Field(ge=0)
    status: str
    holder: Optional[str] = None
    category: Optional[str] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    quantity: int | None = Field(default=None, ge=0)
    status: Optional[str] = None
    holder: Optional[str] = None
    category: Optional[str] = None


class DisciplineRecordCreate(BaseModel):
    memberId: Optional[str] = None
    mssv: str
    name: str
    committee: Optional[str] = None
    absents: int = Field(default=0, ge=0)
    kpi: float = Field(default=0, ge=0)
    disciplineLevel: str = "Khong"
    note: Optional[str] = None


class DisciplineRecordUpdate(BaseModel):
    committee: Optional[str] = None
    absents: int | None = Field(default=None, ge=0)
    kpi: float | None = Field(default=None, ge=0)
    disciplineLevel: Optional[str] = None
    note: Optional[str] = None


class SettingsProfileUpdate(BaseModel):
    fullName: Optional[str] = None
    avatarInitials: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


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
    context: Optional[str] = None
