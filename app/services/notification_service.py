"""
Notification Service
"""

from typing import List, Optional, Any, Dict
import uuid
from sqlalchemy import select, and_, update, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.shopping_list_member import ShoppingListMember
from app.common.enums import NotificationType
from app.websocket.manager import manager
from app.core.logging import get_logger

logger = get_logger(__name__)


class NotificationService:
    """Service for handling notifications."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(
        self,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        payload: Dict[str, Any],
        shopping_list_id: Optional[uuid.UUID] = None,
        send_websocket: bool = True,
    ) -> Notification:
        """
        Create a notification in the database and dispatch via WebSocket.
        """
        notification = Notification(
            user_id=user_id,
            shopping_list_id=shopping_list_id,
            type=notification_type,
            payload=payload,
            is_read=False,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)

        # Dispatch via WebSocket (real-time)
        if send_websocket:
            try:
                await manager.send_to_user(
                    str(user_id),
                    {
                        "type": "notification",
                        "payload": {
                            "id": str(notification.id),
                            "type": notification.type,
                            "data": notification.payload,
                            "shopping_list_id": str(notification.shopping_list_id) if notification.shopping_list_id else None,
                            "created_at": notification.created_at.isoformat(),
                        },
                    },
                )
            except Exception as e:
                logger.error(f"Failed to dispatch WebSocket notification: {e}")

        return notification

    async def get_user_notifications(
        self,
        user_id: uuid.UUID,
        is_read: Optional[bool] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[dict]:
        """
        Get paginated notifications for a user with optional filter.
        """
        query = select(Notification).where(Notification.user_id == user_id)
        
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
        
        query = query.order_by(desc(Notification.created_at)).offset(skip).limit(limit)
        
        result = await self.db.execute(query)
        notifications = result.scalars().all()
        return [
            {
                "id": n.id,
                "user_id": n.user_id,
                "shopping_list_id": n.shopping_list_id,
                "type": n.type,
                "payload": n.payload,
                "is_read": n.is_read,
                "created_at": n.created_at,
            }
            for n in notifications
        ]

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        """Get the count of unread notifications for a user."""
        query = select(func.count(Notification.id)).where(
            and_(Notification.user_id == user_id, Notification.is_read == False)
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def mark_as_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Mark a specific notification as read."""
        query = (
            update(Notification)
            .where(and_(Notification.id == notification_id, Notification.user_id == user_id))
            .values(is_read=True)
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0

    async def mark_all_as_read(self, user_id: uuid.UUID) -> int:
        """Mark all notifications for a user as read."""
        query = (
            update(Notification)
            .where(and_(Notification.user_id == user_id, Notification.is_read == False))
            .values(is_read=True)
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def notify_list_members(
        self,
        list_id: uuid.UUID,
        notification_type: NotificationType,
        payload: Dict[str, Any],
        exclude_user_id: Optional[uuid.UUID] = None,
    ) -> int:
        """
        Notify all members of a shopping list about an event.
        Returns the number of notifications created.
        """
        # Get all members
        result = await self.db.execute(
            select(ShoppingListMember.user_id).where(
                and_(
                    ShoppingListMember.shopping_list_id == list_id,
                    ShoppingListMember.deleted_at.is_(None),
                )
            )
        )
        member_ids = result.scalars().all()
        
        count = 0
        for user_id in member_ids:
            if exclude_user_id and user_id == exclude_user_id:
                continue
            
            # Check if user is already a subscriber of this list
            # If they are, they will receive the 'event' broadcast, so we skip the 'notification' packet
            is_subscriber = False
            if list_id:
                list_str = str(list_id)
                if list_str in manager.list_subscribers:
                    is_subscriber = str(user_id) in manager.list_subscribers[list_str]

            await self.create_notification(
                user_id=user_id,
                notification_type=notification_type,
                payload=payload,
                shopping_list_id=list_id,
                send_websocket=not is_subscriber,
            )
            count += 1
            
        return count
