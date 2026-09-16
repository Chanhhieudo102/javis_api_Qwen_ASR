"""User schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.users.enums.user_role import UserRole


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    """User creation schema."""

    password: str


class UserRegister(BaseModel):
    """User registration schema."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)

    @field_validator("confirm_password")
    def passwords_match(cls, v, info):
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v


class OwnerCreate(BaseModel):
    """Owner creation schema."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    full_name: str | None = None
    phone: str | None = None


class EmployeeCreate(BaseModel):
    """Employee creation schema (created by owner)."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: str | None = None
    phone: str | None = None
    role: UserRole = Field(..., description="Employee role (waiter, chef, bartender, cashier)")
    employee_id: str | None = Field(None, max_length=50, description="Optional employee ID")
    password: str | None = Field(
        None, min_length=8, description="Optional password, auto-generated if not provided"
    )


class UserUpdate(BaseModel):
    """User update schema."""

    full_name: str | None = None
    password: str | None = None


class UserResponse(UserBase):
    """User response schema."""

    id: uuid.UUID
    username: str
    role: UserRole
    phone: str | None = None
    employee_id: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmployeeCreateResponse(BaseModel):
    """Employee creation response with optional generated password."""

    user: UserResponse
    generated_password: str | None = Field(
        None, description="Auto-generated password (only shown once)"
    )

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """User list response schema."""

    users: list[UserResponse]
