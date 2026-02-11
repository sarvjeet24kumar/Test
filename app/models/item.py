"""
Item Model

Represents an item in a shopping list.
"""

from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import String, Integer, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.common.enums import ItemStatus
from app.common.constants import MAX_LENGTH_NAME


class Item(BaseModel):
    """
    Shopping list item entity.
    
    Attributes:
        id: Unique identifier (UUID)
        shopping_list_id: Foreign key to shopping list
        added_by: Foreign key to user who added the item
        name: Item name
        quantity: Item quantity (must be >= 1)
        status: Item status (PENDING or PURCHASED)
    """

    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="check_quantity_positive"),
        Index("idx_items_shopping_list", "shopping_list_id"),
        Index("idx_items_added_by", "added_by"),
    )

    shopping_list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shopping_lists.id", ondelete="CASCADE"),
        nullable=False,
    )
    added_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(MAX_LENGTH_NAME), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[ItemStatus] = mapped_column(
        ENUM(ItemStatus, name="item_status", create_type=True),
        default=ItemStatus.PENDING,
        nullable=False,
    )

    # Relationships
    shopping_list: Mapped["ShoppingList"] = relationship(
        "ShoppingList", back_populates="items"
    )
    added_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="added_items",
        foreign_keys=[added_by],
    )

    def __repr__(self) -> str:
        return f"<Item(id={self.id}, name='{self.name}', status={self.status})>"

    @property
    def is_purchased(self) -> bool:
        return self.status == ItemStatus.PURCHASED
