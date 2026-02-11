"""
Shopping List Member Model

Represents membership in a shopping list with role and permissions.
Handles invitations via status (PENDING/ACCEPTED).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import ForeignKey, UniqueConstraint, Index, DateTime, Boolean, func
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.common.enums import MemberRole

if TYPE_CHECKING:
    from app.models.shopping_list import ShoppingList
    from app.models.user import User


class ShoppingListMember(BaseModel):
    """
    Shopping list membership entity.
    
    Attributes:
        id: Unique identifier (UUID)
        shopping_list_id: Foreign key to shopping list
        user_id: Foreign key to user
        role: Member role (OWNER or MEMBER)
        can_view: Permission to view list
        can_add_item: Permission to add items
        can_update_item: Permission to update items
        can_delete_item: Permission to delete items
        joined_at: Timestamp when membership started
    """

    __tablename__ = "shopping_list_members"
    __table_args__ = (
        UniqueConstraint(
            "shopping_list_id", "user_id", name="uq_members_list_user"
        ),
        Index("idx_members_shopping_list_id", "shopping_list_id"),
        Index("idx_members_user_id", "user_id"),
    )

    shopping_list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shopping_lists.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MemberRole] = mapped_column(
        ENUM(MemberRole, name="member_role", create_type=True),
        default=MemberRole.MEMBER,
        nullable=False,
    )
    can_view: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_add_item: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_update_item: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_delete_item: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    shopping_list: Mapped["ShoppingList"] = relationship(
        "ShoppingList", back_populates="members"
    )
    user: Mapped["User"] = relationship("User", back_populates="list_memberships")

    def __repr__(self) -> str:
        return f"<ShoppingListMember(list_id={self.shopping_list_id}, user_id={self.user_id}, role={self.role})>"

    @property
    def is_owner(self) -> bool:
        return self.role == MemberRole.OWNER
