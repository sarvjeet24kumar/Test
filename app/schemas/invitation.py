"""
Invitation Schemas

Request and response schemas for DB-backed invitation handling.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict

from app.common.enums import MemberRole, InviteStatus


class InviteRequest(BaseModel):
    """Invitation request schema."""

    user_id: UUID


class InviteResponse(BaseModel):
    """Invitation response schema."""

    message: str = "Invitation sent successfully"
    expires_at: datetime


class InvitationAcceptRequest(BaseModel):
    """Accept invitation request."""
    token: str


class InvitationRejectRequest(BaseModel):
    """Reject invitation request."""
    token: str


class InvitationResponse(BaseModel):
    """Full invitation response."""
    id: UUID
    shopping_list_id: UUID
    list_name: Optional[str] = None
    invited_user_id: UUID
    invited_email: Optional[str] = None
    invited_username: Optional[str] = None
    invited_by_user_id: UUID
    invited_by_username: Optional[str] = None
    status: InviteStatus
    expires_at: datetime
    created_at: datetime
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    resent_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
