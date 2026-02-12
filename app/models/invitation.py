"""
Shopping List Invitation Model

Represents a standalone invitation to join a shopping list.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import String, ForeignKey, Index, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.common.enums import InviteStatus
from app.common.constants import MAX_LENGTH_TOKEN

if TYPE_CHECKING:
    from app.models.shopping_list import ShoppingList
    from app.models.user import User


class ShoppingListInvite(BaseModel):
    """
    Shopping list invitation entity.
    
    Attributes:
        id: Unique identifier (UUID)
        shopping_list_id: Foreign key to shopping list
        invited_user_id: Foreign key to user who is invited
        invited_by_user_id: Foreign key to user who sent the invite
        token: Unique token for invitation links
        status: Current status (PENDING, etc.)
        expires_at: When the invite expires
        created_at: Inherited from BaseModel
        accepted_at: When accepted
        rejected_at: When rejected
    """

    __tablename__ = "shopping_list_invites"
    __table_args__ = (
        Index("idx_invites_list_id", "shopping_list_id"),
        Index("idx_invites_invited_user_id", "invited_user_id"),
        Index("idx_invites_invited_by_user_id", "invited_by_user_id"),
        Index("idx_invites_status", "status"),
        Index("idx_invites_token", "token", unique=True),
    )

    shopping_list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shopping_lists.id", ondelete="CASCADE"),
        nullable=False,
    )
    invited_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(MAX_LENGTH_TOKEN), unique=True, nullable=False)
    status: Mapped[InviteStatus] = mapped_column(
        ENUM(InviteStatus, name="invite_status", create_type=True),
        default=InviteStatus.PENDING,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    shopping_list: Mapped["ShoppingList"] = relationship(
        "ShoppingList", back_populates="invites"
    )
    invited_user: Mapped["User"] = relationship(
        "User", 
        foreign_keys=[invited_user_id],
        back_populates="received_invitations"
    )
    invited_by_user: Mapped["User"] = relationship(
        "User", 
        foreign_keys=[invited_by_user_id],
        back_populates="sent_invitations"
    )

    @property
    def list_name(self) -> Optional[str]:
        return self.shopping_list.name if self.shopping_list else None

    @property
    def invited_email(self) -> Optional[str]:
        return self.invited_user.email if self.invited_user else None

    @property
    def invited_username(self) -> Optional[str]:
        return self.invited_user.username if self.invited_user else None

    @property
    def invited_by_username(self) -> Optional[str]:
        return self.invited_by_user.username if self.invited_by_user else None

    def __repr__(self) -> str:
        return f"<ShoppingListInvite(id={self.id}, list_id={self.shopping_list_id}, status={self.status})>"
