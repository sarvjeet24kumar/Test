"""
Chat Service

Handles chat message persistence, membership validation, and real-time broadcasting.
"""

import json
from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.time import get_now

from app.exceptions import NotFoundException, ForbiddenException, ValidationException
from app.models.user import User
from app.models.shopping_list import ShoppingList
from app.models.shopping_list_member import ShoppingListMember
from app.models.chat_message import ChatMessage
from app.services.redis_service import RedisService
from app.websocket.manager import manager
from app.common.enums import UserRole, MemberRole
from app.common.constants import (
    WS_EVENT_CHAT_MESSAGE,
    REDIS_CHANNEL_LIST,
)
from app.core.logging import get_logger

logger = get_logger(__name__)



class ChatService:
    """Service for list-scoped chat operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Membership Check ====================

    async def _verify_membership(
        self, list_id: UUID, user: User
    ) -> ShoppingListMember:
        """
        Verify the user is an ACCEPTED member of the list.
        Tenant Admin is always allowed.
        Returns the membership record.
        """
        # Block Super Admin
        if user.role == UserRole.SUPER_ADMIN:
            raise ForbiddenException("Super Admin cannot access shopping list chat")

        # Tenant Admin bypass — check list belongs to tenant
        if user.role == UserRole.TENANT_ADMIN:
            result = await self.db.execute(
                select(ShoppingList).where(ShoppingList.id == list_id)
            )
            shopping_list = result.scalar_one_or_none()
            if not shopping_list:
                raise NotFoundException("Shopping list not found")
            if shopping_list.tenant_id != user.tenant_id:
                raise ForbiddenException("Cross-tenant access denied")
            # Return a synthetic membership for Tenant Admin
            return None

        # Regular user — must be a member
        result = await self.db.execute(
            select(ShoppingListMember).where(
                and_(
                    ShoppingListMember.shopping_list_id == list_id,
                    ShoppingListMember.user_id == user.id,
                    ShoppingListMember.deleted_at.is_(None),
                )
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise ForbiddenException("You are not a member of this list")

        return membership

    # ==================== Send Message ====================

    async def send_message(
        self, list_id: UUID, user: User, content: str
    ) -> Dict[str, Any]:
        """
        Send a chat message to a shopping list.
        Validates membership, persists, and broadcasts.
        """
        if not content or not content.strip():
            raise ValidationException("Message content cannot be empty")

        await self._verify_membership(list_id, user)

        # Persist message
        message = ChatMessage(
            shopping_list_id=list_id,
            sender_id=user.id,
            content=content.strip(),
        )
        self.db.add(message)
        try:
            await self.db.commit()
            await self.db.refresh(message)
        except Exception as e:
            print(f"ChatService: Commit failed: {e}")
            await self.db.rollback()
            raise

        broadcast_payload = {
            "id": str(message.id),
            "shopping_list_id": str(list_id),
            "sender_id": str(user.id),
            "sender_name": user.username,
            "message": message.content,
            "created_at": message.created_at.isoformat(),
        }

        # Broadcast directly to connected subscribers
        await manager.broadcast_to_list(
            str(list_id),
            {
                "type": WS_EVENT_CHAT_MESSAGE,
                **broadcast_payload
            }
        )

        return broadcast_payload

    # ==================== Get Messages ====================

    async def get_messages(
        self,
        list_id: UUID,
        user: User,
        limit: int = 50,
        after: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load chat history for a shopping list.
        Messages ordered by created_at ASC.
        Supports cursor-based pagination with `after` timestamp.
        """
        await self._verify_membership(list_id, user)

        query = (
            select(ChatMessage)
            .options(selectinload(ChatMessage.sender))
            .where(
                and_(
                    ChatMessage.shopping_list_id == list_id,
                    ChatMessage.deleted_at.is_(None),
                )
            )
        )

        # Cursor pagination
        if after:
            try:
                after_dt = datetime.fromisoformat(after)
                query = query.where(ChatMessage.created_at > after_dt)
            except (ValueError, TypeError):
                pass

        query = query.order_by(ChatMessage.created_at.asc()).limit(limit)
        result = await self.db.execute(query)
        messages = result.scalars().all()

        return [
            {
                "id": str(m.id),
                "shopping_list_id": str(m.shopping_list_id),
                "sender_id": str(m.sender_id),
                "sender_name": m.sender.username if m.sender else "Unknown",
                "message": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]

    # ==================== Delete Message ====================

    async def delete_message(
        self, list_id: UUID, message_id: UUID, user: User
    ) -> None:
        """
        Soft-delete a chat message.
        Only the sender or list owner can delete.
        """
        await self._verify_membership(list_id, user)

        result = await self.db.execute(
            select(ChatMessage).where(
                and_(
                    ChatMessage.id == message_id,
                    ChatMessage.shopping_list_id == list_id,
                    ChatMessage.deleted_at.is_(None),
                )
            )
        )
        message = result.scalar_one_or_none()
        if not message:
            raise NotFoundException("Message not found")

        # Check permission: sender or list owner
        is_sender = message.sender_id == user.id
        is_tenant_admin = user.role == UserRole.TENANT_ADMIN

        # Check if list owner
        is_owner = False
        if not is_sender and not is_tenant_admin:
            result = await self.db.execute(
                select(ShoppingList).where(ShoppingList.id == list_id)
            )
            shopping_list = result.scalar_one_or_none()
            if shopping_list and shopping_list.owner_id == user.id:
                is_owner = True

        if not is_sender and not is_owner and not is_tenant_admin:
            raise ForbiddenException("Only the message sender or list owner can delete messages")

        message.deleted_at = get_now()
        await self.db.commit()
