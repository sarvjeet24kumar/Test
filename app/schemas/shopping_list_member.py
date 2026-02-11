"""
Shopping List Member Schemas

Request and response schemas for list membership management.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr

from app.models.shopping_list_member import MemberRole


class MemberResponse(BaseModel):
    """Member response schema with permission flags."""

    id: UUID
    user_id: UUID
    username: str
    email: str
    role: MemberRole
    can_add_item: bool = False
    can_update_item: bool = False
    can_delete_item: bool = False
    joined_at: datetime

    class Config:
        from_attributes = True


class UpdateMemberPermissions(BaseModel):
    """Schema for updating member permissions (Owner/Tenant Admin only)."""

    can_add_item: Optional[bool] = None
    can_update_item: Optional[bool] = None
    can_delete_item: Optional[bool] = None


class InviteRequest(BaseModel):
    """Invitation request schema."""

    email: EmailStr


class InviteResponse(BaseModel):
    """Invitation response schema."""

    message: str = "Invitation sent successfully"
    expires_at: datetime


class RemoveMemberResponse(BaseModel):
    """Member removal response."""

    message: str = "Member removed successfully"


class LeaveListResponse(BaseModel):
    """Leave list response."""

    message: str = "Successfully left the list"
