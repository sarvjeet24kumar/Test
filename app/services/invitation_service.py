"""
Invitation Service

Handles DB-backed shopping list invitations with full state machine:
PENDING → ACCEPTED / REJECTED / CANCELLED / EXPIRED
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.security import create_invitation_token, decode_invitation_token
from app.exceptions import (
    NotFoundException,
    ForbiddenException,
    ValidationException,
    ConflictException,
)
from app.exceptions.base import MiniMartException
from app.models.user import User
from app.models.shopping_list import ShoppingList
from app.models.shopping_list_member import ShoppingListMember
from app.models.invitation import ShoppingListInvite
from app.services.redis_service import RedisService
from app.services.email_service import EmailService
from app.services.notification_service import NotificationService
from app.websocket.manager import manager
from app.common.enums import UserRole, MemberRole, InviteStatus, NotificationType
from app.common.constants import (
    WS_EVENT_INVITE_CREATED,
    WS_EVENT_INVITE_ACCEPTED,
    WS_EVENT_INVITE_REJECTED,
    WS_EVENT_INVITE_CANCELLED,
    WS_EVENT_MEMBER_JOINED,
    REDIS_CHANNEL_LIST,
)
from app.core.logging import get_logger
from jose import JWTError

logger = get_logger(__name__)

class InvitationService:
    """Service for DB-backed invitation operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Create Invite ====================

    async def send_invitation(
        self,
        list_id: UUID,
        user_id: UUID,
        inviter: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> datetime:
        """
        Create a DB-backed invitation to join a shopping list.

        Returns:
            Expiration datetime of the invite.
        """
        # Block Super Admin
        if inviter.role == UserRole.SUPER_ADMIN:
            raise ForbiddenException("Super Admin cannot access shopping list operations")

        # Get shopping list
        result = await self.db.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        shopping_list = result.scalar_one_or_none()

        if not shopping_list:
            raise NotFoundException("Shopping list not found")

        # Verify tenant isolation
        if shopping_list.tenant_id != inviter.tenant_id:
            raise ForbiddenException("Cross-tenant access denied")

        # Verify inviter is owner or tenant admin
        if inviter.role != UserRole.TENANT_ADMIN and shopping_list.owner_id != inviter.id:
            raise ForbiddenException(
                "Only the list owner or tenant admin can send invitations"
            )

        # Find invitee user
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.id == user_id,
                    User.tenant_id == inviter.tenant_id,
                )
            )
        )
        invitee = result.scalar_one_or_none()

        if not invitee:
            raise NotFoundException(
                "User not found in this tenant. Only users within the same tenant can be invited."
            )

        if not invitee.is_active:
            raise ValidationException("Cannot invite inactive user")

        # Check if already a member
        result = await self.db.execute(
            select(ShoppingListMember).where(
                and_(
                    ShoppingListMember.shopping_list_id == list_id,
                    ShoppingListMember.user_id == invitee.id,
                    ShoppingListMember.deleted_at.is_(None),
                )
            )
        )
        if result.scalar_one_or_none():
            raise ConflictException("User is already a member of this list")

        # Check for existing PENDING invite
        result = await self.db.execute(
            select(ShoppingListInvite).where(
                and_(
                    ShoppingListInvite.shopping_list_id == list_id,
                    ShoppingListInvite.invited_user_id == invitee.id,
                    ShoppingListInvite.status == InviteStatus.PENDING,
                )
            )
        )
        existing_invite = result.scalar_one_or_none()
        if existing_invite:
            raise ConflictException(
                "A pending invitation already exists for this user. Use resend to send again."
            )

        # Generate token
        expires_delta = timedelta(hours=settings.invitation_token_expire_hours)
        token = create_invitation_token(
            list_id=list_id,
            email=invitee.email,
            tenant_id=inviter.tenant_id,
            inviter_id=inviter.id,
            expires_delta=expires_delta,
        )

        expires_at = datetime.now(timezone.utc) + expires_delta

        # Create DB row
        invite = ShoppingListInvite(
            shopping_list_id=list_id,
            invited_user_id=invitee.id,
            invited_by_user_id=inviter.id,
            token=token,
            status=InviteStatus.PENDING,
            expires_at=expires_at,
        )
        self.db.add(invite)
        await self.db.commit()
        await self.db.refresh(invite)

        # Send email
        accept_url = f"{settings.invitation_base_url}/accept?token={token}"
        reject_url = f"{settings.invitation_base_url}/reject?token={token}"

        if background_tasks:
            background_tasks.add_task(
                EmailService.send_invitation_email,
                to_email=invitee.email,
                inviter_name=inviter.username,
                list_name=shopping_list.name,
                accept_url=accept_url,
                reject_url=reject_url,
            )
        else:
            await EmailService.send_invitation_email(
                to_email=invitee.email,
                inviter_name=inviter.username,
                list_name=shopping_list.name,
                accept_url=accept_url,
                reject_url=reject_url,
            )

        # Broadcast WS event
        await self._broadcast(list_id, "invite_created", {
            "invite_id": str(invite.id),
            "invited_user_id": str(invitee.id),
            "invited_email": invitee.email,
            "invited_by": str(inviter.id),
        })

        # Create Persistent Notification
        notification_service = NotificationService(self.db)
        await notification_service.create_notification(
            user_id=invitee.id,
            notification_type=NotificationType.LIST_INVITE,
            payload={
                "invite_id": str(invite.id),
                "list_name": shopping_list.name,
                "inviter_username": inviter.username,
            },
            shopping_list_id=list_id,
        )

        return expires_at

    # ==================== Accept Invite ====================

    async def accept_invitation(self, token: str, user: User) -> ShoppingList:
        """
        Accept an invitation. Validates token, DB state, and creates membership.
        """
        # Decode token
        try:
            payload = decode_invitation_token(token)
        except JWTError as e:
            raise ValidationException(f"Invalid or expired invitation token: {str(e)}")

        # Validate email matches
        if payload["email"] != user.email:
            raise ForbiddenException(
                "This invitation was sent to a different email address"
            )

        # Validate tenant matches
        if UUID(payload["tenant_id"]) != user.tenant_id:
            raise ForbiddenException("Cross-tenant invitation not allowed")

        # Find the DB invite by token
        result = await self.db.execute(
            select(ShoppingListInvite).where(ShoppingListInvite.token == token)
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise ValidationException("Invitation not found")

        # Validate state
        if invite.status != InviteStatus.PENDING:
            raise MiniMartException(
                status_code=400,
                code="INVITE_NOT_PENDING",
                message=f"Invitation has already been {invite.status.value.lower()}.",
            )

        # Check expired
        if invite.expires_at < datetime.now(timezone.utc):
            invite.status = InviteStatus.EXPIRED
            await self.db.commit()
            raise ValidationException("Invitation has expired")

        list_id = invite.shopping_list_id

        # Verify list still exists
        result = await self.db.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        shopping_list = result.scalar_one_or_none()

        if not shopping_list:
            raise NotFoundException("Shopping list no longer exists")

        # Check if already a member
        result = await self.db.execute(
            select(ShoppingListMember).where(
                and_(
                    ShoppingListMember.shopping_list_id == list_id,
                    ShoppingListMember.user_id == user.id,
                    ShoppingListMember.deleted_at.is_(None),
                )
            )
        )
        if result.scalar_one_or_none():
            invite.status = InviteStatus.ACCEPTED
            invite.accepted_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise ConflictException("User is already a member of this list")

        # Create membership
        membership = ShoppingListMember(
            shopping_list_id=list_id,
            user_id=user.id,
            role=MemberRole.MEMBER,
        )
        self.db.add(membership)

        # Update invite status
        invite.status = InviteStatus.ACCEPTED
        invite.accepted_at = datetime.now(timezone.utc)
        await self.db.commit()

        # Broadcast WS event
        await self._broadcast(list_id, "member_joined", {
            "user_id": str(user.id),
            "username": user.username,
            "role": MemberRole.MEMBER.value,
        })

        # Create Persistent Notification for the inviter
        notification_service = NotificationService(self.db)
        await notification_service.create_notification(
            user_id=invite.invited_by_user_id,
            notification_type=NotificationType.INVITE_ACCEPTED,
            payload={
                "username": user.username,
                "list_name": shopping_list.name,
            },
            shopping_list_id=list_id,
        )

        await self.db.refresh(shopping_list)
        return shopping_list

    # ==================== Reject Invite ====================

    async def reject_invitation(self, token: str) -> bool:
        """
        Reject an invitation. Updates DB state.
        """
        try:
            payload = decode_invitation_token(token)
        except JWTError:
            # Invalid token — just return silently
            return True

        # Find DB invite
        result = await self.db.execute(
            select(ShoppingListInvite).where(ShoppingListInvite.token == token)
        )
        invite = result.scalar_one_or_none()

        if not invite or invite.status != InviteStatus.PENDING:
            return True

        # Update state
        invite.status = InviteStatus.REJECTED
        invite.rejected_at = datetime.now(timezone.utc)
        await self.db.commit()

        # Broadcast WS event
        await self._broadcast(invite.shopping_list_id, "invite_rejected", {
            "invite_id": str(invite.id),
            "invited_user_id": str(invite.invited_user_id),
        })

        # Create Persistent Notification for the inviter
        notification_service = NotificationService(self.db)
        await notification_service.create_notification(
            user_id=invite.invited_by_user_id,
            notification_type=NotificationType.INVITE_REJECTED,
            payload={
                "username": "Someone",  # We don't necessarily have the user object here, but we can infer it
                "invite_id": str(invite.id),
            },
            shopping_list_id=invite.shopping_list_id,
        )

        return True

    # ==================== Cancel Invite ====================

    async def cancel_invitation(
        self, invite_id: UUID, user: User
    ) -> None:
        """
        Cancel an invitation. Owner / Tenant Admin only.
        """
        if user.role == UserRole.SUPER_ADMIN:
            raise ForbiddenException("Super Admin cannot access shopping list operations")

        result = await self.db.execute(
            select(ShoppingListInvite)
            .options(selectinload(ShoppingListInvite.shopping_list))
            .where(ShoppingListInvite.id == invite_id)
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise NotFoundException("Invitation not found")

        shopping_list = invite.shopping_list

        # Verify tenant
        if shopping_list.tenant_id != user.tenant_id:
            raise ForbiddenException("Cross-tenant access denied")

        # Verify permission (owner or tenant admin)
        if user.role != UserRole.TENANT_ADMIN and shopping_list.owner_id != user.id:
            raise ForbiddenException("Only the list owner or tenant admin can cancel invitations")

        if invite.status != InviteStatus.PENDING:
            raise MiniMartException(
                status_code=400,
                code="INVITE_NOT_PENDING",
                message=f"Cannot cancel — invitation is already {invite.status.value.lower()}.",
            )

        invite.status = InviteStatus.CANCELLED
        invite.cancelled_at = datetime.now(timezone.utc)
        await self.db.commit()

        # Broadcast WS event
        await self._broadcast(invite.shopping_list_id, "invite_cancelled", {
            "invite_id": str(invite.id),
            "invited_user_id": str(invite.invited_user_id),
        })

    # ==================== Resend Invite ====================

    async def resend_invitation(
        self,
        invite_id: UUID,
        user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> datetime:
        """
        Resend an invitation — rotates token, resets expiry.
        """
        if user.role == UserRole.SUPER_ADMIN:
            raise ForbiddenException("Super Admin cannot access shopping list operations")

        result = await self.db.execute(
            select(ShoppingListInvite)
            .options(
                selectinload(ShoppingListInvite.shopping_list),
                selectinload(ShoppingListInvite.invited_user),
            )
            .where(ShoppingListInvite.id == invite_id)
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise NotFoundException("Invitation not found")

        shopping_list = invite.shopping_list

        # Verify tenant
        if shopping_list.tenant_id != user.tenant_id:
            raise ForbiddenException("Cross-tenant access denied")

        # Verify permission
        if user.role != UserRole.TENANT_ADMIN and shopping_list.owner_id != user.id:
            raise ForbiddenException("Only the list owner or tenant admin can resend invitations")

        if invite.status != InviteStatus.PENDING:
            raise MiniMartException(
                status_code=400,
                code="INVITE_NOT_PENDING",
                message=f"Cannot resend — invitation is already {invite.status.value.lower()}.",
            )

        # Rotate token
        expires_delta = timedelta(hours=settings.invitation_token_expire_hours)
        new_token = create_invitation_token(
            list_id=invite.shopping_list_id,
            email=invite.invited_user.email,
            tenant_id=user.tenant_id,
            inviter_id=user.id,
            expires_delta=expires_delta,
        )

        invite.token = new_token
        invite.expires_at = datetime.now(timezone.utc) + expires_delta
        invite.resent_at = datetime.now(timezone.utc)
        await self.db.commit()

        # Send email
        accept_url = f"{settings.invitation_base_url}/accept?token={new_token}"
        reject_url = f"{settings.invitation_base_url}/reject?token={new_token}"

        if background_tasks:
            background_tasks.add_task(
                EmailService.send_invitation_email,
                to_email=invite.invited_user.email,
                inviter_name=user.username,
                list_name=shopping_list.name,
                accept_url=accept_url,
                reject_url=reject_url,
            )
        else:
            await EmailService.send_invitation_email(
                to_email=invite.invited_user.email,
                inviter_name=user.username,
                list_name=shopping_list.name,
                accept_url=accept_url,
                reject_url=reject_url,
            )

        return invite.expires_at

    # ==================== Get Invites ====================

    async def get_list_invites(
        self,
        list_id: UUID,
        user: User,
        status_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[dict], int]:
        """
        Get invitations for a specific list. Owner / Tenant Admin only.
        """
        if user.role == UserRole.SUPER_ADMIN:
            raise ForbiddenException("Super Admin cannot access shopping list operations")

        # Verify list
        result = await self.db.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        shopping_list = result.scalar_one_or_none()
        if not shopping_list:
            raise NotFoundException("Shopping list not found")

        if shopping_list.tenant_id != user.tenant_id:
            raise ForbiddenException("Cross-tenant access denied")

        if user.role != UserRole.TENANT_ADMIN and shopping_list.owner_id != user.id:
            raise ForbiddenException("Only the list owner or tenant admin can view invitations")

        # Build query
        query = select(ShoppingListInvite).options(
            selectinload(ShoppingListInvite.invited_user),
            selectinload(ShoppingListInvite.invited_by_user),
            selectinload(ShoppingListInvite.shopping_list),
        ).where(ShoppingListInvite.shopping_list_id == list_id)

        if status_filter and status_filter.upper() in InviteStatus.__members__:
            query = query.where(
                ShoppingListInvite.status == InviteStatus(status_filter.upper())
            )

        # Count
        from sqlalchemy import func
        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        # Fetch
        query = query.order_by(ShoppingListInvite.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        invites = result.scalars().all()

        return [self._to_detail_dict(i) for i in invites], total

    async def get_my_invites(
        self,
        user: User,
        status_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[dict], int]:
        """
        Get invitations sent to the current user across all lists.
        """
        query = select(ShoppingListInvite).options(
            selectinload(ShoppingListInvite.shopping_list),
            selectinload(ShoppingListInvite.invited_by_user),
            selectinload(ShoppingListInvite.invited_user),
        ).where(
            and_(
                ShoppingListInvite.invited_user_id == user.id,
            )
        )

        if status_filter and status_filter.upper() in InviteStatus.__members__:
            query = query.where(
                ShoppingListInvite.status == InviteStatus(status_filter.upper())
            )

        from sqlalchemy import func
        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        query = query.order_by(ShoppingListInvite.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        invites = result.scalars().all()

        return [self._to_detail_dict(i) for i in invites], total

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

    # ==================== Expire Stale Invites ====================
    ...

    async def expire_stale_invites(self) -> int:
        """
        Mark expired PENDING invites as EXPIRED. Returns count of updated rows.
        """
        from sqlalchemy import update

        now = datetime.now(timezone.utc)
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

    # ==================== Helpers ====================

    async def _broadcast(
        self, list_id: UUID, event_type: str, data: dict
    ) -> None:
        """Broadcast event directly to connected subscribers."""
        await manager.broadcast_event(str(list_id), event_type, data)
