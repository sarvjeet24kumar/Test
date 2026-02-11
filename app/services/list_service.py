"""
Shopping List Service

Handles shopping list and item management with role-based permission enforcement.

Permission Matrix:
- Super Admin: NO access to any shopping list operations
- Tenant Admin: Full access to ALL lists in their tenant
- Owner: Full access to their own list
- Member: View access + item operations governed by permission flags
"""

from typing import List, Optional, Tuple
from uuid import UUID
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from app.exceptions import NotFoundException, ForbiddenException
from app.models.shopping_list import ShoppingList
from app.models.shopping_list_member import ShoppingListMember, MemberRole
from app.models.item import Item, ItemStatus
from app.models.user import User, UserRole
from app.schemas.shopping_list import ShoppingListCreate, ShoppingListUpdate
from app.schemas.item import ItemCreate, ItemUpdate
from app.services.redis_service import RedisService


class ListService:
    """Service for shopping list operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Access Control Helper ====================

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

        Args:
            list_id: Shopping list UUID
            user: Requesting user
            require_owner_or_admin: If True, only Owner or Tenant Admin allowed

        Returns:
            Tuple of (ShoppingList, membership or None)

        Raises:
            ForbiddenException: If Super Admin, cross-tenant, or insufficient access
            NotFoundException: If list not found
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
            # Find their membership if they happen to be a member, else None
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

    # ==================== Shopping List Operations ====================

    async def create_list(
        self, user: User, data: ShoppingListCreate
    ) -> ShoppingList:
        """
        Create a new shopping list.
        Allowed: Tenant Admin, User. Blocked: Super Admin.
        """
        self._block_super_admin(user)

        shopping_list = ShoppingList(
            tenant_id=user.tenant_id,
            owner_id=user.id,
            name=data.name,
        )
        self.db.add(shopping_list)
        await self.db.flush()

        # Create owner membership with full permissions
        membership = ShoppingListMember(
            shopping_list_id=shopping_list.id,
            user_id=user.id,
            role=MemberRole.OWNER,
            can_view=True,
            can_add_item=True,
            can_update_item=True,
            can_delete_item=True,
        )
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(shopping_list)

        return shopping_list

    async def get_list(
        self, list_id: UUID, user: User
    ) -> ShoppingList:
        """
        Get a shopping list with access check.
        Allowed: Tenant Admin (any list in tenant), Owner, Member.
        Blocked: Super Admin, non-members.
        """
        shopping_list, _ = await self._get_list_with_access(list_id, user)
        return shopping_list

    async def get_user_lists(
        self, user: User, skip: int = 0, limit: int = 100
    ) -> tuple[List[dict], int]:
        """
        Get shopping lists visible to the user.
        - Tenant Admin: ALL lists in their tenant
        - Owner/Member: Lists they are a member of
        """
        self._block_super_admin(user)

        if user.role == UserRole.TENANT_ADMIN:
            # Tenant Admin sees all lists in their tenant
            count_result = await self.db.execute(
                select(func.count()).select_from(ShoppingList).where(
                    ShoppingList.tenant_id == user.tenant_id
                )
            )
            total = count_result.scalar_one()

            result = await self.db.execute(
                select(ShoppingList)
                .options(
                    selectinload(ShoppingList.items),
                    selectinload(ShoppingList.members),
                )
                .where(ShoppingList.tenant_id == user.tenant_id)
                .offset(skip)
                .limit(limit)
            )
            shopping_lists = result.scalars().all()

            lists = []
            for shopping_list in shopping_lists:
                # Check if admin is a member to get their role
                admin_membership = next(
                    (m for m in shopping_list.members if m.user_id == user.id), None
                )
                lists.append({
                    "id": shopping_list.id,
                    "name": shopping_list.name,
                    "role": admin_membership.role.value if admin_membership else "ADMIN",
                    "item_count": len(shopping_list.items),
                    "member_count": len(shopping_list.members),
                    "created_at": shopping_list.created_at,
                })

            return lists, total
        else:
            # Regular users: only their memberships
            count_result = await self.db.execute(
                select(func.count()).where(ShoppingListMember.user_id == user.id)
            )
            total = count_result.scalar_one()

            result = await self.db.execute(
                select(ShoppingListMember)
                .options(
                    selectinload(ShoppingListMember.shopping_list)
                    .selectinload(ShoppingList.items),
                    selectinload(ShoppingListMember.shopping_list)
                    .selectinload(ShoppingList.members),
                )
                .where(ShoppingListMember.user_id == user.id)
                .offset(skip)
                .limit(limit)
            )
            memberships = result.scalars().all()

            lists = []
            for membership in memberships:
                shopping_list = membership.shopping_list
                lists.append({
                    "id": shopping_list.id,
                    "name": shopping_list.name,
                    "role": membership.role.value,
                    "item_count": len(shopping_list.items),
                    "member_count": len(shopping_list.members),
                    "created_at": shopping_list.created_at,
                })

            return lists, total

    async def update_list(
        self, list_id: UUID, user: User, data: ShoppingListUpdate
    ) -> ShoppingList:
        """
        Update a shopping list.
        Allowed: Tenant Admin, Owner. Blocked: Super Admin, Member.
        """
        shopping_list, _ = await self._get_list_with_access(
            list_id, user, require_owner_or_admin=True
        )

        if data.name is not None:
            shopping_list.name = data.name

        await self.db.commit()
        await self.db.refresh(shopping_list)
        return shopping_list

    async def delete_list(self, list_id: UUID, user: User) -> bool:
        """
        Delete a shopping list.
        Allowed: Tenant Admin, Owner. Blocked: Super Admin, Member.
        """
        shopping_list, _ = await self._get_list_with_access(
            list_id, user, require_owner_or_admin=True
        )

        await self.db.delete(shopping_list)
        await self.db.commit()
        return True

    # ==================== Member Operations ====================

    async def get_members(
        self, list_id: UUID, user: User, skip: int = 0, limit: int = 100
    ) -> tuple[List[ShoppingListMember], int]:
        """
        Get all members of a shopping list.
        Allowed: Tenant Admin, Owner, Member. Blocked: Super Admin.
        """
        await self._get_list_with_access(list_id, user)

        count_result = await self.db.execute(
            select(func.count()).where(ShoppingListMember.shopping_list_id == list_id)
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(ShoppingListMember)
            .options(selectinload(ShoppingListMember.user))
            .where(ShoppingListMember.shopping_list_id == list_id)
            .offset(skip)
            .limit(limit)
        )
        items = list(result.scalars().all())

        return items, total

    async def remove_member(
        self, list_id: UUID, member_user_id: UUID, user: User
    ) -> bool:
        """
        Remove a member from a shopping list.
        Allowed: Tenant Admin, Owner. Blocked: Super Admin, Member.
        """
        shopping_list, _ = await self._get_list_with_access(
            list_id, user, require_owner_or_admin=True
        )

        if member_user_id == shopping_list.owner_id:
            raise ForbiddenException("Cannot remove the owner from the list")

        # Find and remove membership
        result = await self.db.execute(
            select(ShoppingListMember).where(
                and_(
                    ShoppingListMember.shopping_list_id == list_id,
                    ShoppingListMember.user_id == member_user_id,
                )
            )
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise NotFoundException("Member not found")

        await self.db.delete(membership)
        await self.db.commit()

        # Publish event for WebSocket disconnection
        await self._publish_event(
            list_id,
            "member_removed",
            {"user_id": str(member_user_id)},
        )

        return True

    async def leave_list(self, list_id: UUID, user: User) -> bool:
        """
        Leave a shopping list (member only, not owner).
        """
        shopping_list, _ = await self._get_list_with_access(list_id, user)

        if shopping_list.owner_id == user.id:
            raise ForbiddenException("Owner cannot leave their own list")

        # Find and remove membership
        result = await self.db.execute(
            select(ShoppingListMember).where(
                and_(
                    ShoppingListMember.shopping_list_id == list_id,
                    ShoppingListMember.user_id == user.id,
                )
            )
        )
        membership = result.scalar_one_or_none()

        if membership:
            await self.db.delete(membership)
            await self.db.commit()

            # Publish event
            await self._publish_event(
                list_id,
                "member_left",
                {"user_id": str(user.id)},
            )

        return True

    async def update_member_permissions(
        self,
        list_id: UUID,
        member_user_id: UUID,
        user: User,
        data,
    ) -> ShoppingListMember:
        """
        Update a member's permission flags.
        Allowed: Tenant Admin, Owner. Blocked: Super Admin, Member.
        Cannot change owner permissions.
        """
        shopping_list, _ = await self._get_list_with_access(
            list_id, user, require_owner_or_admin=True
        )

        if member_user_id == shopping_list.owner_id:
            raise ForbiddenException("Cannot modify the owner's permissions")

        # Find membership
        result = await self.db.execute(
            select(ShoppingListMember)
            .options(selectinload(ShoppingListMember.user))
            .where(
                and_(
                    ShoppingListMember.shopping_list_id == list_id,
                    ShoppingListMember.user_id == member_user_id,
                )
            )
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise NotFoundException("Member not found")

        # Update permission flags
        if data.can_add_item is not None:
            membership.can_add_item = data.can_add_item
        if data.can_update_item is not None:
            membership.can_update_item = data.can_update_item
        if data.can_delete_item is not None:
            membership.can_delete_item = data.can_delete_item

        await self.db.commit()
        await self.db.refresh(membership)

        return membership

    # ==================== Item Operations ====================

    def _check_item_permission(
        self, user: User, membership: Optional[ShoppingListMember], permission: str
    ) -> None:
        """
        Check if user has a specific item permission.

        Tenant Admin and Owner always have full item permissions.
        Members are governed by permission flags on their membership.

        Args:
            user: Requesting user
            membership: User's membership (None for Tenant Admin without membership)
            permission: One of 'can_add_item', 'can_update_item', 'can_delete_item', 'can_view'
        """
        # Tenant Admin always allowed
        if user.role == UserRole.TENANT_ADMIN:
            return

        # Must have membership at this point
        if not membership:
            raise ForbiddenException("You are not a member of this list")

        # Owner always allowed
        if membership.role == MemberRole.OWNER:
            return

        # Member: check the specific permission flag
        if not getattr(membership, permission, False):
            raise ForbiddenException(
                f"You don't have permission to perform this action"
            )

    async def add_item(
        self, list_id: UUID, user: User, data: ItemCreate
    ) -> Item:
        """
        Add an item to a shopping list.
        Allowed: Tenant Admin, Owner, Member (if can_add_item). Blocked: Super Admin.
        """
        shopping_list, membership = await self._get_list_with_access(list_id, user)
        self._check_item_permission(user, membership, "can_add_item")

        item = Item(
            shopping_list_id=list_id,
            added_by=user.id,
            name=data.name,
            quantity=data.quantity,
            status=ItemStatus.PENDING,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)

        # Publish event
        await self._publish_event(
            list_id,
            "item_added",
            {
                "id": str(item.id),
                "name": item.name,
                "quantity": item.quantity,
                "status": item.status.value,
                "added_by": str(user.id),
            },
        )

        return item

    async def get_items(
        self, list_id: UUID, user: User, skip: int = 0, limit: int = 100
    ) -> tuple[List[Item], int]:
        """
        Get all items in a shopping list.
        Allowed: Tenant Admin, Owner, Member (if can_view). Blocked: Super Admin.
        """
        shopping_list, membership = await self._get_list_with_access(list_id, user)
        self._check_item_permission(user, membership, "can_view")

        count_result = await self.db.execute(
            select(func.count()).where(Item.shopping_list_id == list_id)
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(Item)
            .where(Item.shopping_list_id == list_id)
            .order_by(Item.created_at)
            .offset(skip)
            .limit(limit)
        )
        items = list(result.scalars().all())

        return items, total

    async def update_item(
        self, item_id: UUID, user: User, data: ItemUpdate
    ) -> Item:
        """
        Update an item.
        Allowed: Tenant Admin, Owner, Member (if can_update_item). Blocked: Super Admin.
        """
        self._block_super_admin(user)

        result = await self.db.execute(
            select(Item).where(Item.id == item_id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise NotFoundException("Item not found")

        # Verify list access and item permission
        shopping_list, membership = await self._get_list_with_access(
            item.shopping_list_id, user
        )
        self._check_item_permission(user, membership, "can_update_item")

        if data.name is not None:
            item.name = data.name
        if data.quantity is not None:
            item.quantity = data.quantity
        if data.status is not None:
            item.status = data.status

        await self.db.commit()
        await self.db.refresh(item)

        # Publish event
        await self._publish_event(
            item.shopping_list_id,
            "item_updated",
            {
                "id": str(item.id),
                "name": item.name,
                "quantity": item.quantity,
                "status": item.status.value,
            },
        )

        return item

    async def delete_item(self, item_id: UUID, user: User) -> bool:
        """
        Delete an item.
        Allowed: Tenant Admin, Owner, Member (if can_delete_item). Blocked: Super Admin.
        """
        self._block_super_admin(user)

        result = await self.db.execute(
            select(Item).where(Item.id == item_id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise NotFoundException("Item not found")

        # Verify list access and item permission
        list_id = item.shopping_list_id
        shopping_list, membership = await self._get_list_with_access(list_id, user)
        self._check_item_permission(user, membership, "can_delete_item")

        await self.db.delete(item)
        await self.db.commit()

        # Publish event
        await self._publish_event(
            list_id,
            "item_deleted",
            {"id": str(item_id)},
        )

        return True

    # ==================== Helper Methods ====================

    async def _publish_event(
        self, list_id: UUID, event_type: str, data: dict
    ) -> None:
        """Publish event to Redis for WebSocket broadcast."""
        channel = f"list:{list_id}"
        message = json.dumps({
            "event": event_type,
            "list_id": str(list_id),
            "data": data,
        })
        await RedisService.publish_event(channel, message)
