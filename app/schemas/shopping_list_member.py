"""
Shopping List Member Schemas

Request and response schemas for list membership management.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from app.schemas.common import NormalizedModel


from app.common.enums import MemberRole


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

    model_config = ConfigDict(from_attributes=True)


class UpdateMemberPermissions(NormalizedModel):
    """Schema for updating member permissions (Owner/Tenant Admin only)."""

    can_add_item: Optional[bool] = None
    can_update_item: Optional[bool] = None
    can_delete_item: Optional[bool] = None




class RemoveMemberResponse(BaseModel):
    """Member removal response."""

    message: str = "Member removed successfully"


class LeaveListResponse(BaseModel):
    """Leave list response."""

    message: str = "Successfully left the list"
