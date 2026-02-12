"""
Notification Schemas
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.common.enums import NotificationType


class NotificationResponse(BaseModel):
    """Notification response schema."""

    id: UUID
    user_id: UUID
    shopping_list_id: Optional[UUID] = None
    type: NotificationType
    payload: Dict[str, Any] = Field(default_factory=dict)
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationUpdate(BaseModel):
    """Notification update schema (mostly for marking as read)."""

    is_read: bool


class NotificationFilter(BaseModel):
    """Query parameters for filtering notifications."""

    is_read: Optional[bool] = None
