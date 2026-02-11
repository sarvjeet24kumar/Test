"""
User Schemas

Request and response schemas for user management.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr, ConfigDict

from app.common.enums import UserRole


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_]+$")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class UserSignupRequest(UserBase):
    password: str = Field(..., min_length=8, max_length=128)

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    is_active: bool
    is_email_verified: bool

    model_config = ConfigDict(from_attributes=True)
    
class UserCreate(UserBase):
    """User creation schema."""

    password: str = Field(..., min_length=8, max_length=128)
    tenant_id: Optional[UUID] = None


class UserUpdate(BaseModel):
    """User update schema."""

    username: Optional[str] = Field(None, min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_]+$")
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    deleted_at: Optional[datetime] = None


class UserResponse(UserBase):
    """User response schema."""

    id: UUID
    tenant_id: Optional[UUID] = None
    role: UserRole
    is_email_verified: bool
    is_active: bool
    deleted_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserWithTenantResponse(UserResponse):
    """User response with tenant details."""

    tenant_name: str


class UserProfileResponse(BaseModel):
    """User profile response (self)."""

    id: UUID
    email: str
    username: str
    first_name: str
    last_name: str
    tenant_id: Optional[UUID] = None
    tenant_name: Optional[str] = None
    role: UserRole
    is_email_verified: bool
    deleted_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    """Change password request."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
