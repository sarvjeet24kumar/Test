"""
Shopping List Member Management Service
"""

from typing import List
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from app.models.shopping_list_member import ShoppingListMember
from app.models.user import User
from app.services.notification_service import NotificationService
from app.services.shopping_list.base import BaseListService
from app.common.enums import NotificationType
from app.common.constants import (
    WS_EVENT_MEMBER_REMOVED,
    WS_EVENT_MEMBER_LEFT,
    WS_EVENT_PERMISSIONS_UPDATED,
    DEFAULT_PAGE_SIZE,
)
from app.exceptions import NotFoundException, ForbiddenException
from app.core.logging import get_logger

logger = get_logger(__name__)

class ListMemberService(BaseListService):
    """Handles membership and permission operations."""

    async def get_members(
        self, list_id: UUID, user: User, skip: int = 0, limit: int = DEFAULT_PAGE_SIZE
    ) -> tuple[List[dict], int]:
        """Get all members of a shopping list."""
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
        members = result.scalars().all()

        return [
            {
                "id": m.id,
                "user_id": m.user_id,
                "username": m.user.username if m.user else "Unknown",
                "email": m.user.email if m.user else "Unknown",
                "role": m.role.value,
                "can_view": m.can_view,
                "can_add_item": m.can_add_item,
                "can_update_item": m.can_update_item,
                "can_delete_item": m.can_delete_item,
                "joined_at": m.joined_at,
            }
            for m in members
        ], total

    async def notify_member_removed(self, list_id: UUID, member_user_id: UUID, user: User, shopping_list_name: str):
        """Helper to create notification when a member is removed."""
        notification_service = NotificationService(self.db)
        await notification_service.create_notification(
            user_id=member_user_id,
            notification_type=NotificationType.MEMBER_REMOVED,
            payload={
                "list_name": shopping_list_name,
                "remover_username": user.username,
            },
            shopping_list_id=list_id,
        )

    async def remove_member(
        self, list_id: UUID, member_user_id: UUID, user: User
    ) -> bool:
        """Remove a member from a shopping list."""
        shopping_list, _ = await self._get_list_with_access(
            list_id, user, require_owner_or_admin=True
        )

        if member_user_id == shopping_list.owner_id:
            raise ForbiddenException("Cannot remove the owner from the list")

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

        logger.info("Member removed from list: list_id=%s", list_id)

        await self._publish_event(
            list_id,
            WS_EVENT_MEMBER_REMOVED,
            {"user_id": str(member_user_id)},
            exclude_user_id=user.id,
        )

        await self.notify_member_removed(list_id, member_user_id, user, shopping_list.name)

        return True

    async def leave_list(self, list_id: UUID, user: User) -> bool:
        """Leave a shopping list."""
        shopping_list, _ = await self._get_list_with_access(list_id, user)

        if shopping_list.owner_id == user.id:
            raise ForbiddenException("Owner cannot leave their own list")

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

            logger.info("Member left list: list_id=%s", list_id)

            await self._publish_event(list_id, WS_EVENT_MEMBER_LEFT, {"user_id": str(user.id)}, exclude_user_id=user.id)

            notification_service = NotificationService(self.db)
            await notification_service.notify_list_members(
                list_id=list_id,
                notification_type=NotificationType.LIST_UPDATED,
                payload={
                    "username": user.username,
                    "event": "member_left",
                    "list_name": shopping_list.name,
                },
                exclude_user_id=user.id,
            )

        return True

    async def update_member_permissions(
        self,
        list_id: UUID,
        member_user_id: UUID,
        user: User,
        data,
    ) -> ShoppingListMember:
        """Update a member's permission flags."""
        shopping_list, _ = await self._get_list_with_access(
            list_id, user, require_owner_or_admin=True
        )

        if member_user_id == shopping_list.owner_id:
            raise ForbiddenException("Cannot modify the owner's permissions")

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

        if data.can_add_item is not None:
            membership.can_add_item = data.can_add_item
        if data.can_update_item is not None:
            membership.can_update_item = data.can_update_item
        if data.can_delete_item is not None:
            membership.can_delete_item = data.can_delete_item

        await self.db.commit()
        await self.db.refresh(membership)

        logger.info("Permissions updated: list_id=%s member=%s", list_id, member_user_id)

        await self._publish_event(
            list_id,
            WS_EVENT_PERMISSIONS_UPDATED,
            {
                "user_id": str(member_user_id),
                "can_add_item": membership.can_add_item,
                "can_update_item": membership.can_update_item,
                "can_delete_item": membership.can_delete_item,
            },
        )

        return membership
