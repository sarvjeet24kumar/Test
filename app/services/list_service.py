"""
Shopping List Service

Handles shopping list and item management.
"""

from typing import List, Optional
from uuid import UUID
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from app.exceptions import NotFoundException, ForbiddenException
from app.models.shopping_list import ShoppingList
from app.models.shopping_list_member import ShoppingListMember, MemberRole
from app.models.item import Item, ItemStatus
from app.models.user import User
from app.schemas.shopping_list import ShoppingListCreate, ShoppingListUpdate
from app.schemas.item import ItemCreate, ItemUpdate
from app.services.redis_service import RedisService


class ListService:
    """Service for shopping list operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Shopping List Operations ====================

    async def create_list(
        self, user: User, data: ShoppingListCreate
    ) -> ShoppingList:
        """
        Create a new shopping list.
        
        Args:
            user: Creating user
            data: List creation data
        
        Returns:
            Created ShoppingList with owner membership
        """
        # Create shopping list
        shopping_list = ShoppingList(
            tenant_id=user.tenant_id,
            owner_id=user.id,
            name=data.name,
        )
        self.db.add(shopping_list)
        await self.db.flush()

        # Create owner membership
        membership = ShoppingListMember(
            shopping_list_id=shopping_list.id,
            user_id=user.id,
            role=MemberRole.OWNER,
        )
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(shopping_list)

        return shopping_list

    async def get_list(
        self, list_id: UUID, user: User
    ) -> ShoppingList:
        """
        Get a shopping list with membership check.
        
        Args:
            list_id: Shopping list UUID
            user: Requesting user
        
        Returns:
            ShoppingList
        
        Raises:
            NotFoundException: If list not found
            ForbiddenException: If cross-tenant or not a member
        """
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

        # Check membership
        is_member = any(m.user_id == user.id for m in shopping_list.members)
        if not is_member:
            raise ForbiddenException("You are not a member of this list")

        return shopping_list

    async def get_user_lists(
        self, user: User, skip: int = 0, limit: int = 100
    ) -> tuple[List[dict], int]:
        """
        Get all shopping lists the user is a member of.
        
        Args:
            user: Requesting user
            skip: Records to skip
            limit: Maximum records to return
        
        Returns:
            Tuple of (List of summaries, Total Count)
        """
        # Get total count
        count_result = await self.db.execute(
            select(func.count()).where(ShoppingListMember.user_id == user.id)
        )
        total = count_result.scalar_one()

        # Get memberships with list info
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
        Update a shopping list (owner only).
        
        Args:
            list_id: Shopping list UUID
            user: Requesting user
            data: Update data
        
        Returns:
            Updated ShoppingList
        
        Raises:
            ForbiddenException: If not owner
        """
        shopping_list = await self.get_list(list_id, user)

        # Check ownership
        if shopping_list.owner_id != user.id:
            raise ForbiddenException("Only the owner can update this list")

        if data.name is not None:
            shopping_list.name = data.name

        await self.db.commit()
        await self.db.refresh(shopping_list)
        return shopping_list

    async def delete_list(self, list_id: UUID, user: User) -> bool:
        """
        Delete a shopping list (owner only).
        
        Args:
            list_id: Shopping list UUID
            user: Requesting user
        
        Returns:
            bool: True if deleted
        
        Raises:
            ForbiddenException: If not owner
        """
        shopping_list = await self.get_list(list_id, user)

        if shopping_list.owner_id != user.id:
            raise ForbiddenException("Only the owner can delete this list")

        await self.db.delete(shopping_list)
        await self.db.commit()
        return True

    # ==================== Member Operations ====================

    async def get_members(
        self, list_id: UUID, user: User, skip: int = 0, limit: int = 100
    ) -> tuple[List[ShoppingListMember], int]:
        """
        Get all members of a shopping list.
        
        Args:
            list_id: Shopping list UUID
            user: Requesting user
            skip: Records to skip
            limit: Maximum records to return
        
        Returns:
            Tuple of (List of members, Total Count)
        """
        # Verify access
        await self.get_list(list_id, user)

        # Get total count
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
        Remove a member from a shopping list (owner only).
        
        Args:
            list_id: Shopping list UUID
            member_user_id: User ID to remove
            user: Requesting user (must be owner)
        
        Returns:
            bool: True if removed
        
        Raises:
            ForbiddenException: If not owner or trying to remove owner
        """
        shopping_list = await self.get_list(list_id, user)

        if shopping_list.owner_id != user.id:
            raise ForbiddenException("Only the owner can remove members")

        if member_user_id == user.id:
            raise ForbiddenException("Owner cannot remove themselves")

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
        
        Args:
            list_id: Shopping list UUID
            user: Requesting user
        
        Returns:
            bool: True if left
        
        Raises:
            ForbiddenException: If owner tries to leave
        """
        shopping_list = await self.get_list(list_id, user)

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

    # ==================== Item Operations ====================

    async def add_item(
        self, list_id: UUID, user: User, data: ItemCreate
    ) -> Item:
        """
        Add an item to a shopping list.
        
        Args:
            list_id: Shopping list UUID
            user: Requesting user
            data: Item data
        
        Returns:
            Created Item
        """
        # Verify access
        await self.get_list(list_id, user)

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
        
        Args:
            list_id: Shopping list UUID
            user: Requesting user
            skip: Records to skip
            limit: Maximum records to return
        
        Returns:
            Tuple of (List of Items, Total Count)
        """
        # Verify access
        await self.get_list(list_id, user)

        # Get total count
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
        
        Args:
            item_id: Item UUID
            user: Requesting user
            data: Update data
        
        Returns:
            Updated Item
        """
        result = await self.db.execute(
            select(Item).where(Item.id == item_id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise NotFoundException("Item not found")

        # Verify list access
        await self.get_list(item.shopping_list_id, user)

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
        
        Args:
            item_id: Item UUID
            user: Requesting user
        
        Returns:
            bool: True if deleted
        """
        result = await self.db.execute(
            select(Item).where(Item.id == item_id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise NotFoundException("Item not found")

        # Verify list access
        list_id = item.shopping_list_id
        await self.get_list(list_id, user)

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
