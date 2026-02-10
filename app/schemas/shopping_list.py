"""
Shopping List Schemas

Request and response schemas for shopping list management.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field


class ShoppingListBase(BaseModel):
    """Base shopping list schema."""

    name: str = Field(..., min_length=1, max_length=255)


class ShoppingListCreate(ShoppingListBase):
    """Shopping list creation schema."""

    pass


class ShoppingListUpdate(BaseModel):
    """Shopping list update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)


class MemberBrief(BaseModel):
    """Brief member info for list response."""

    user_id: UUID
    username: str
    role: str
    joined_at: datetime

    class Config:
        from_attributes = True


class ShoppingListResponse(ShoppingListBase):
    """Shopping list response schema."""

    id: UUID
    tenant_id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ItemBrief(BaseModel):
    """Brief item info for list response."""

    id: UUID
    name: str
    quantity: int
    status: str
    added_by: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True


class ShoppingListDetailResponse(ShoppingListResponse):
    """Detailed shopping list response with members and items."""

    members: List[MemberBrief] = []
    items: List[ItemBrief] = []
    item_count: int = 0
    pending_count: int = 0
    purchased_count: int = 0


class ShoppingListSummaryResponse(BaseModel):
    """Summary response for list of shopping lists."""

    id: UUID
    name: str
    role: str  # User's role in this list
    item_count: int
    member_count: int
    created_at: datetime

    class Config:
        from_attributes = True
