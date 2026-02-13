"""
Base Invitation Service

Contains shared logic for invitation operations.
"""

from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.websocket.manager import manager
from app.models.invitation import ShoppingListInvite

class BaseInvitationService:
    """Base class for all invitation services."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _broadcast(
        self, list_id: UUID, event_type: str, data: dict, exclude_user_id: Optional[UUID] = None
    ) -> None:
        """Broadcast event directly to connected subscribers."""
        await manager.broadcast_event(
            str(list_id), 
            event_type, 
            data, 
            exclude_user_id=str(exclude_user_id) if exclude_user_id else None
        )

    def _to_detail_dict(self, invite: ShoppingListInvite) -> dict:
        """Convert an invitation ORM object to a detail dictionary."""
        return {
            "id": invite.id,
            "shopping_list_id": invite.shopping_list_id,
            "list_name": invite.shopping_list.name if invite.shopping_list else None,
            "invited_user_id": invite.invited_user_id,
            "invited_email": invite.invited_user.email if invite.invited_user else None,
            "invited_username": invite.invited_user.username if invite.invited_user else None,
            "invited_by_user_id": invite.invited_by_user_id,
            "invited_by_username": invite.invited_by_user.username if invite.invited_by_user else None,
            "status": invite.status,
            "expires_at": invite.expires_at,
            "created_at": invite.created_at,
            "accepted_at": invite.accepted_at,
            "rejected_at": invite.rejected_at,
            "cancelled_at": invite.cancelled_at,
            "resent_at": invite.resent_at,
        }
