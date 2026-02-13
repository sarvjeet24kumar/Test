"""
Shopping List Item Management Service
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func

from app.models.item import Item
from app.models.user import User
from app.schemas.item import ItemCreate, ItemUpdate
from app.services.notification_service import NotificationService
from app.services.shopping_list.base import BaseListService
from app.common.enums import ItemStatus, NotificationType
from app.common.constants import (
    WS_EVENT_ITEM_ADDED,
    WS_EVENT_ITEM_UPDATED,
    WS_EVENT_ITEM_DELETED,
    DEFAULT_PAGE_SIZE,
)
from app.exceptions import NotFoundException
from app.core.logging import get_logger

logger = get_logger(__name__)

class ListItemService(BaseListService):
    """Handles operations on shopping list items."""

    async def add_item(
        self, list_id: UUID, user: User, data: ItemCreate
    ) -> Item:
        """Add an item to a shopping list."""
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

        logger.info("Item added: item_id=%s list_id=%s", item.id, list_id)

        await self._publish_event(
            list_id,
            WS_EVENT_ITEM_ADDED,
            {
                "id": str(item.id),
                "name": item.name,
                "quantity": item.quantity,
                "status": item.status.value,
                "added_by": str(user.id),
            },
            exclude_user_id=user.id,
        )

        notification_service = NotificationService(self.db)
        await notification_service.notify_list_members(
            list_id=list_id,
            notification_type=NotificationType.ITEM_ADDED,
            payload={
                "item_name": item.name,
                "added_by": user.username,
                "list_name": shopping_list.name,
            },
            exclude_user_id=user.id,
        )

        return item

    async def get_items(
        self, list_id: UUID, user: User, skip: int = 0, limit: int = DEFAULT_PAGE_SIZE
    ) -> tuple[List[dict], int]:
        """Get all items in a shopping list."""
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
        items = result.scalars().all()

        return [
            {
                "id": i.id,
                "name": i.name,
                "quantity": i.quantity,
                "status": i.status.value,
                "added_by": i.added_by,
                "created_at": i.created_at,
            }
            for i in items
        ], total

    async def get_item(
        self, list_id: UUID, item_id: UUID, user: User
    ) -> Item:
        """Get a specific item ensuring it belongs to the given list."""
        self._block_super_admin(user)

        result = await self.db.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one_or_none()

        if not item or item.shopping_list_id != list_id:
            raise NotFoundException("Item not found in this list")

        shopping_list, membership = await self._get_list_with_access(list_id, user)
        self._check_item_permission(user, membership, "can_view")

        return item

    async def update_item(
        self, item_id: UUID, user: User, data: ItemUpdate
    ) -> Item:
        """Update an item (standalone)."""
        self._block_super_admin(user)

        result = await self.db.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one_or_none()

        if not item:
            raise NotFoundException("Item not found")

        shopping_list, membership = await self._get_list_with_access(item.shopping_list_id, user)
        self._check_item_permission(user, membership, "can_update_item")

        if data.name is not None:
            item.name = data.name
        if data.quantity is not None:
            item.quantity = data.quantity
        if data.status is not None:
            item.status = data.status

        await self.db.commit()
        await self.db.refresh(item)

        await self._publish_event(
            item.shopping_list_id,
            WS_EVENT_ITEM_UPDATED,
            {
                "id": str(item.id),
                "name": item.name,
                "quantity": item.quantity,
                "status": item.status.value,
            },
            exclude_user_id=user.id,
        )

        notification_service = NotificationService(self.db)
        notif_type = NotificationType.ITEM_PURCHASED if item.status == ItemStatus.PURCHASED else NotificationType.ITEM_UPDATED
        await notification_service.notify_list_members(
            list_id=item.shopping_list_id,
            notification_type=notif_type,
            payload={
                "item_name": item.name,
                "updated_by": user.username,
                "status": item.status.value,
                "list_name": shopping_list.name,
            },
            exclude_user_id=user.id,
        )

        return item

    async def delete_item(self, item_id: UUID, user: User) -> bool:
        """Delete an item (standalone)."""
        self._block_super_admin(user)

        result = await self.db.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one_or_none()

        if not item:
            raise NotFoundException("Item not found")

        list_id = item.shopping_list_id
        shopping_list, membership = await self._get_list_with_access(list_id, user)
        self._check_item_permission(user, membership, "can_delete_item")

        await self.db.delete(item)
        await self.db.commit()

        await self._publish_event(list_id, WS_EVENT_ITEM_DELETED, {"id": str(item_id)}, exclude_user_id=user.id)

        notification_service = NotificationService(self.db)
        await notification_service.notify_list_members(
            list_id=list_id,
            notification_type=NotificationType.ITEM_DELETED,
            payload={"deleted_by": user.username, "list_name": shopping_list.name},
            exclude_user_id=user.id,
        )

        return True

    async def update_item_scoped(
        self, list_id: UUID, item_id: UUID, user: User, data
    ) -> Item:
        """Update an item ensuring it belongs to the given list."""
        return await self.update_item(item_id, user, data)

    async def delete_item_scoped(
        self, list_id: UUID, item_id: UUID, user: User
    ) -> bool:
        """Delete an item ensuring it belongs to the given list."""
        return await self.delete_item(item_id, user)
