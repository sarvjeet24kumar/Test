"""
Shopping List Model

Represents a shopping list owned by a user within a tenant.
"""

from typing import TYPE_CHECKING, List
import uuid

from sqlalchemy import String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.shopping_list_member import ShoppingListMember
    from app.models.item import Item
    from app.models.chat_message import ChatMessage
    from app.models.notification import Notification
    from app.models.invitation import ShoppingListInvite


class ShoppingList(BaseModel):
    """
    Shopping list entity.
    
    Attributes:
        id: Unique identifier (UUID)
        tenant_id: Foreign key to tenant (for isolation)
        owner_id: Foreign key to the user who created the list
        name: Display name of the list
    """

    __tablename__ = "shopping_lists"
    __table_args__ = (
        Index("idx_shopping_lists_tenant_id", "tenant_id"),
        Index("idx_shopping_lists_owner_id", "owner_id"),
        Index("idx_shopping_lists_created_at", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="shopping_lists")
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="owned_lists",
        foreign_keys=[owner_id],
    )
    members: Mapped[List["ShoppingListMember"]] = relationship(
        "ShoppingListMember",
        back_populates="shopping_list",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    items: Mapped[List["Item"]] = relationship(
        "Item",
        back_populates="shopping_list",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Item.created_at",
    )
    chat_messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="shopping_list",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ChatMessage.created_at",
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        back_populates="shopping_list",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    invites: Mapped[List["ShoppingListInvite"]] = relationship(
        "ShoppingListInvite",
        back_populates="shopping_list",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<ShoppingList(id={self.id}, name='{self.name}')>"
