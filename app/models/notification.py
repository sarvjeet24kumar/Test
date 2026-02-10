"""
Notification Model

Represents user notifications for various events.
"""

from typing import TYPE_CHECKING, Optional, Dict, Any
import uuid
import enum

from sqlalchemy import ForeignKey, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID, ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.shopping_list import ShoppingList


class NotificationType(str, enum.Enum):
    """Types of notifications."""

    LIST_INVITE = "LIST_INVITE"
    INVITE_ACCEPTED = "INVITE_ACCEPTED"
    INVITE_REJECTED = "INVITE_REJECTED"
    ITEM_ADDED = "ITEM_ADDED"
    ITEM_PURCHASED = "ITEM_PURCHASED"
    CHAT_MESSAGE = "CHAT_MESSAGE"


class Notification(BaseModel):
    """
    Notification entity for user notifications.
    
    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key to user receiving the notification
        shopping_list_id: Foreign key to shopping list (nullable)
        type: Type of notification
        payload: Additional notification data (JSONB)
        is_read: Whether the notification has been read
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_user_id", "user_id"),
        Index("idx_notifications_user_unread", "user_id", "is_read"),
        Index("idx_notifications_created_at", "user_id", "created_at"),
        Index("idx_notifications_type", "user_id", "type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    shopping_list_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shopping_lists.id", ondelete="CASCADE"),
        nullable=True,
    )
    type: Mapped[NotificationType] = mapped_column(
        ENUM(NotificationType, name="notification_type", create_type=True),
        nullable=False,
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notifications")
    shopping_list: Mapped[Optional["ShoppingList"]] = relationship(
        "ShoppingList", back_populates="notifications"
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type})>"

    @property
    def is_unread(self) -> bool:
        return not self.is_read
