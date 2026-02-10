"""
Tenant Schemas

Request and response schemas for tenant management.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr


class TenantBase(BaseModel):
    """Base tenant schema."""

    name: str = Field(..., min_length=1, max_length=255)


class TenantCreate(BaseModel):
    """Tenant creation schema (name and slug only)."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")


class TenantUpdate(BaseModel):
    """Tenant update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    is_active: Optional[bool] = None
    deleted_at: Optional[datetime] = None


class TenantResponse(TenantBase):
    """Tenant response schema."""

    id: UUID
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Forward reference for circular import
class UserBriefResponse(BaseModel):
    """Brief user response for embedding."""

    id: UUID
    email: str
    username: str

    class Config:
        from_attributes = True
