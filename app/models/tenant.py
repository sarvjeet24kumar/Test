"""
Tenant Model

Represents a tenant/organization in the multi-tenant system.
All users, shopping lists, and items belong to a tenant.
"""

from typing import TYPE_CHECKING, List

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.shopping_list import ShoppingList


class Tenant(BaseModel):
    """
    Tenant entity for multi-tenancy.
    
    Attributes:
        id: Unique identifier (UUID)
        name: Tenant display name
        is_active: Whether the tenant is active
        created_at: Creation timestamp
        updated_at: Last update timestamp
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    shopping_lists: Mapped[List["ShoppingList"]] = relationship(
        "ShoppingList",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}')>"
