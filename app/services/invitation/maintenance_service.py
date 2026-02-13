"""
Invitation Maintenance Service
"""

from datetime import datetime
from sqlalchemy import and_, update

from app.core.time import get_now

from app.models.invitation import ShoppingListInvite
from app.services.invitation.base import BaseInvitationService
from app.common.enums import InviteStatus

class InvitationMaintenanceService(BaseInvitationService):
    """Handles cleanup and background maintenance of invitations."""

    async def expire_stale_invites(self) -> int:
        """Mark expired PENDING invites as EXPIRED."""
        now = get_now()
        stmt = (
            update(ShoppingListInvite)
            .where(
                and_(
                    ShoppingListInvite.status == InviteStatus.PENDING,
                    ShoppingListInvite.expires_at < now,
                )
            )
            .values(status=InviteStatus.EXPIRED)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount
