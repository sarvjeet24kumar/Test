"""
Base Shopping List Service

Contains shared logic for access control, permissions, and internal event publishing.
"""

from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.exceptions import NotFoundException, ForbiddenException
from app.models.shopping_list import ShoppingList
from app.models.shopping_list_member import ShoppingListMember
from app.models.user import User
from app.websocket.manager import manager
from app.common.enums import UserRole, MemberRole

class BaseListService:
    """Foundational class for shopping list-related services."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _block_super_admin(self, user: User) -> None:
        """Block Super Admin from all shopping list operations."""
        if user.role == UserRole.SUPER_ADMIN:
            raise ForbiddenException("Super Admin cannot access shopping list operations")

    async def _get_list_with_access(
        self,
        list_id: UUID,
        user: User,
        require_owner_or_admin: bool = False,
    ) -> Tuple[ShoppingList, Optional[ShoppingListMember]]:
        """
        Central access gate for shopping list operations.
        """
        self._block_super_admin(user)

        result = await self.db.execute(
            select(ShoppingList)
            .options(
                selectinload(ShoppingList.members).selectinload(ShoppingListMember.user),
                selectinload(ShoppingList.items),
            )
            .where(ShoppingList.id == list_id)
        )
        shopping_list = result.scalar_one_or_none()

        if not shopping_list:
            raise NotFoundException("Shopping list not found")

        # Tenant isolation
        if shopping_list.tenant_id != user.tenant_id:
            raise ForbiddenException("Cross-tenant access denied")

        # Tenant Admin: full access to any list in their tenant
        if user.role == UserRole.TENANT_ADMIN:
            membership = next(
                (m for m in shopping_list.members if m.user_id == user.id), None
            )
            return shopping_list, membership

        # Regular users: must be a member
        membership = next(
            (m for m in shopping_list.members if m.user_id == user.id), None
        )
        if not membership:
            raise ForbiddenException("You are not a member of this list")

        # If owner/admin required, check role
        if require_owner_or_admin and membership.role != MemberRole.OWNER:
            raise ForbiddenException("Only the owner can perform this action")

        return shopping_list, membership

    def _check_item_permission(
        self, user: User, membership: Optional[ShoppingListMember], permission: str
    ) -> None:
        """
        Check if user has a specific item permission.
        """
        if user.role == UserRole.TENANT_ADMIN:
            return

        if not membership:
            raise ForbiddenException("You are not a member of this list")

        if membership.role == MemberRole.OWNER:
            return

        if not getattr(membership, permission, False):
            raise ForbiddenException("You don't have permission to perform this action")

    async def _publish_event(
        self, list_id: UUID, event_type: str, data: dict, exclude_user_id: Optional[UUID] = None
    ) -> None:
        """Broadcast event directly to connected subscribers."""
        await manager.broadcast_event(
            str(list_id), 
            event_type, 
            data, 
            exclude_user_id=str(exclude_user_id) if exclude_user_id else None
        )
