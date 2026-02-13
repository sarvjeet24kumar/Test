"""
Item Schemas

Request and response schemas for shopping list items.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.common import NormalizedModel

from app.common.enums import ItemStatus


class ItemBase(NormalizedModel):
    """Base item schema."""

    name: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(default=1, ge=1)


class ItemCreate(ItemBase):
    """Item creation schema."""

    pass


class ItemUpdate(NormalizedModel):
    """Item update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    quantity: Optional[int] = Field(None, ge=1)
    status: Optional[ItemStatus] = None


class ItemResponse(NormalizedModel):
    """Item response schema."""

    id: UUID
    name: str
    quantity: int
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
