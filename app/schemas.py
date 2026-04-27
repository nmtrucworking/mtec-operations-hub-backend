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
    date: date
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
