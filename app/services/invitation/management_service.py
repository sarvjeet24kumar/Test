"""
Invitation Management Service
"""

from datetime import datetime, timedelta
from uuid import UUID
from typing import Optional, List

from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.security import create_invitation_token
from app.core.time import get_now
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
from app.services.email_service import EmailService
from app.services.notification_service import NotificationService
from app.services.invitation.base import BaseInvitationService
from app.common.enums import UserRole, InviteStatus, NotificationType
from app.core.logging import get_logger

logger = get_logger(__name__)

class InvitationManagementService(BaseInvitationService):
    """Handles creation and administrative management of invitations."""

    async def send_invitation(
        self,
        list_id: UUID,
        user_id: UUID,
        inviter: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> datetime:
        """Create a DB-backed invitation to join a shopping list."""
        if inviter.role == UserRole.SUPER_ADMIN:
            raise ForbiddenException("Super Admin cannot access shopping list operations")

        result = await self.db.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        shopping_list = result.scalar_one_or_none()

        if not shopping_list:
            raise NotFoundException("Shopping list not found")

        if shopping_list.tenant_id != inviter.tenant_id:
            raise ForbiddenException("Cross-tenant access denied")

        if inviter.role != UserRole.TENANT_ADMIN and shopping_list.owner_id != inviter.id:
            raise ForbiddenException(
                "Only the list owner or tenant admin can send invitations"
            )

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
            raise NotFoundException("User not found in this tenant.")

        if not invitee.is_active:
            raise ValidationException("Cannot invite inactive user")

        result = await self.db.execute(
            select(ShoppingListMember).where(
                and_(
                    ShoppingListMember.shopping_list_id == list_id,
                    ShoppingListMember.user_id == invitee.id,
                )
            )
        )
        if result.scalar_one_or_none():
            raise ConflictException("User is already a member of this list")

        result = await self.db.execute(
            select(ShoppingListInvite).where(
                and_(
                    ShoppingListInvite.shopping_list_id == list_id,
                    ShoppingListInvite.invited_user_id == invitee.id,
                    ShoppingListInvite.status == InviteStatus.PENDING,
                )
            )
        )
        if result.scalar_one_or_none():
            raise ConflictException("A pending invitation already exists for this user.")

        expires_delta = timedelta(hours=settings.invitation_token_expire_hours)
        token = create_invitation_token(
            list_id=list_id,
            email=invitee.email,
            tenant_id=inviter.tenant_id,
            inviter_id=inviter.id,
            expires_delta=expires_delta,
        )

        expires_at = get_now() + expires_delta

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

        await self._broadcast(list_id, "invite_created", {
            "invite_id": str(invite.id),
            "invited_user_id": str(invitee.id),
            "invited_email": invitee.email,
            "invited_by": str(inviter.id),
        }, exclude_user_id=inviter.id)

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

    async def cancel_invitation(
        self, invite_id: UUID, user: User
    ) -> None:
        """Cancel an invitation."""
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

        if shopping_list.tenant_id != user.tenant_id:
            raise ForbiddenException("Cross-tenant access denied")

        if user.role != UserRole.TENANT_ADMIN and shopping_list.owner_id != user.id:
            raise ForbiddenException("Only the list owner or tenant admin can cancel invitations")

        if invite.status != InviteStatus.PENDING:
            raise MiniMartException(
                status_code=400,
                code="INVITE_NOT_PENDING",
                message=f"Cannot cancel — invitation is already {invite.status.value.lower()}.",
            )

        invite.status = InviteStatus.CANCELLED
        invite.cancelled_at = get_now()
        await self.db.commit()

        await self._broadcast(invite.shopping_list_id, "invite_cancelled", {
            "invite_id": str(invite.id),
            "invited_user_id": str(invite.invited_user_id),
        })

    async def resend_invitation(
        self,
        invite_id: UUID,
        user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> datetime:
        """Resend an invitation."""
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

        if shopping_list.tenant_id != user.tenant_id:
            raise ForbiddenException("Cross-tenant access denied")

        if user.role != UserRole.TENANT_ADMIN and shopping_list.owner_id != user.id:
            raise ForbiddenException("Only the list owner or tenant admin can resend invitations")

        if invite.status != InviteStatus.PENDING:
            raise MiniMartException(
                status_code=400,
                code="INVITE_NOT_PENDING",
                message=f"Cannot resend — invitation is already {invite.status.value.lower()}.",
            )

        expires_delta = timedelta(hours=settings.invitation_token_expire_hours)
        new_token = create_invitation_token(
            list_id=invite.shopping_list_id,
            email=invite.invited_user.email,
            tenant_id=user.tenant_id,
            inviter_id=user.id,
            expires_delta=expires_delta,
        )

        invite.token = new_token
        invite.expires_at = get_now() + expires_delta
        invite.resent_at = get_now()
        await self.db.commit()

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

    async def get_list_invites(
        self,
        list_id: UUID,
        user: User,
        status_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[dict], int]:
        """Get invitations for a specific list."""
        if user.role == UserRole.SUPER_ADMIN:
            raise ForbiddenException("Super Admin cannot access shopping list operations")

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

        query = select(ShoppingListInvite).options(
            selectinload(ShoppingListInvite.invited_user),
            selectinload(ShoppingListInvite.invited_by_user),
            selectinload(ShoppingListInvite.shopping_list),
        ).where(ShoppingListInvite.shopping_list_id == list_id)

        if status_filter and status_filter.upper() in InviteStatus.__members__:
            query = query.where(
                ShoppingListInvite.status == InviteStatus(status_filter.upper())
            )

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

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
        """Get invitations sent to the current user."""
        query = select(ShoppingListInvite).options(
            selectinload(ShoppingListInvite.shopping_list),
            selectinload(ShoppingListInvite.invited_by_user),
            selectinload(ShoppingListInvite.invited_user),
        ).where(ShoppingListInvite.invited_user_id == user.id)

        if status_filter and status_filter.upper() in InviteStatus.__members__:
            query = query.where(
                ShoppingListInvite.status == InviteStatus(status_filter.upper())
            )

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        query = query.order_by(ShoppingListInvite.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        invites = result.scalars().all()

        return [self._to_detail_dict(i) for i in invites], total
