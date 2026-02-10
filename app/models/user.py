"""
User Model

Represents users in the system with role-based access control.
Users belong to exactly one tenant.
"""

from typing import TYPE_CHECKING, List, Optional
import uuid
import enum

from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.shopping_list import ShoppingList
    from app.models.shopping_list_member import ShoppingListMember
    from app.models.item import Item
    from app.models.chat_message import ChatMessage
    from app.models.notification import Notification
    from app.models.invitation import ShoppingListInvite


class UserRole(str, enum.Enum):
    """User roles for platform-level access control."""

    SUPER_ADMIN = "SUPER_ADMIN"
    TENANT_ADMIN = "TENANT_ADMIN"
    USER = "USER"


class User(BaseModel):
    """
    User entity with tenant association.

    Attributes:
        id: Unique identifier (UUID)
        tenant_id: Foreign key to tenant
        first_name: User's first name
        last_name: User's last name
        username: Unique per tenant
        email: Email address (unique per tenant)
        password: Hashed password
        role: Platform-level role (SUPER_ADMIN, TENANT_ADMIN, USER)
        is_email_verified: Email verification status
        is_active: Account active status
    """

    __tablename__ = "users"
    __table_args__ = (
        # Standard tenant-scoped uniqueness
        UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        
        # Global uniqueness for users without a tenant (Super Admins)
        Index("uq_users_global_username", "username", unique=True, postgresql_where="tenant_id IS NULL"),
        Index("uq_users_global_email", "email", unique=True, postgresql_where="tenant_id IS NULL"),
        
        Index("idx_users_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        ENUM(UserRole, name="user_role", create_type=True),
        default=UserRole.USER,
        nullable=False,
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    owned_lists: Mapped[List["ShoppingList"]] = relationship(
        "ShoppingList",
        back_populates="owner",
        foreign_keys="ShoppingList.owner_id",
        lazy="selectin",
    )
    list_memberships: Mapped[List["ShoppingListMember"]] = relationship(
        "ShoppingListMember",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    added_items: Mapped[List["Item"]] = relationship(
        "Item",
        back_populates="added_by_user",
        foreign_keys="Item.added_by",
        lazy="selectin",
    )
    sent_messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="sender",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    sent_invitations: Mapped[List["ShoppingListInvite"]] = relationship(
        "ShoppingListInvite",
        back_populates="invited_by_user",
        foreign_keys="[ShoppingListInvite.invited_by_user_id]",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    received_invitations: Mapped[List["ShoppingListInvite"]] = relationship(
        "ShoppingListInvite",
        back_populates="invited_user",
        foreign_keys="[ShoppingListInvite.invited_user_id]",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role={self.role})>"

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_tenant_admin(self) -> bool:
        return self.role == UserRole.TENANT_ADMIN

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
