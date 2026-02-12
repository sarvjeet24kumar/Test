"""
Item Schemas

Request and response schemas for shopping list items.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.common.enums import ItemStatus


class ItemBase(BaseModel):
    """Base item schema."""

    name: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(default=1, ge=1)


class ItemCreate(ItemBase):
    """Item creation schema."""

    pass


class ItemUpdate(BaseModel):
    """Item update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    quantity: Optional[int] = Field(None, ge=1)
    status: Optional[ItemStatus] = None


class ItemResponse(ItemBase):
    """Item response schema."""

    id: UUID
    shopping_list_id: UUID
    added_by: Optional[UUID]
    added_by_username: Optional[str] = None
    status: ItemStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ItemStatusUpdate(BaseModel):
    """Quick status update schema."""

    status: ItemStatus
