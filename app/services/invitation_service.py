"""
Invitation Service

Handles stateless, token-based list invitations.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID
import json
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.core.security import create_invitation_token, decode_invitation_token
from app.exceptions import (
    NotFoundException,
    ForbiddenException,
    ValidationException,
    ConflictException,
)
from app.models.user import User, UserRole
from app.models.shopping_list import ShoppingList
from app.models.shopping_list_member import ShoppingListMember, MemberRole
from app.services.redis_service import RedisService
from app.services.email_service import EmailService
from jose import JWTError
from fastapi import BackgroundTasks


class InvitationService:
    """Service for invitation operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_invitation(
        self, 
        list_id: UUID, 
        invitee_email: str, 
        inviter: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> datetime:
        """
        Send an invitation to join a shopping list.
        
        Args:
            list_id: Shopping list UUID
            invitee_email: Email of user to invite
            inviter: User sending the invitation
        
        Returns:
            datetime: Expiration time of the invitation
        
        Raises:
            NotFoundException: If list or user not found
            ForbiddenException: If not list owner
            ConflictException: If user already a member
            ValidationException: If inviting user from different tenant
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
            raise ForbiddenException("Only the list owner or tenant admin can send invitations")

        # Find invitee user
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.email == invitee_email,
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
                )
            )
        )
        if result.scalar_one_or_none():
            raise ConflictException("User is already a member of this list")

        # Generate invitation token
        expires_delta = timedelta(hours=settings.invitation_token_expire_hours)
        token = create_invitation_token(
            list_id=list_id,
            email=invitee_email,
            tenant_id=inviter.tenant_id,
            inviter_id=inviter.id,
            expires_delta=expires_delta,
        )

        # Decode to get jti for Redis storage
        payload = decode_invitation_token(token)
        token_id = payload["jti"]
        expire_seconds = settings.invitation_token_expire_hours * 3600

        # Store token in Redis
        await RedisService.store_invitation_token(
            token_id=token_id,
            list_id=str(list_id),
            expire_seconds=expire_seconds,
        )

        # Generate URLs
        accept_url = f"{settings.invitation_base_url}/accept?token={token}"
        reject_url = f"{settings.invitation_base_url}/reject?token={token}"

        # Send email
        if background_tasks:
            background_tasks.add_task(
                EmailService.send_invitation_email,
                to_email=invitee_email,
                inviter_name=inviter.username,
                list_name=shopping_list.name,
                accept_url=accept_url,
                reject_url=reject_url,
            )
        else:
            await EmailService.send_invitation_email(
                to_email=invitee_email,
                inviter_name=inviter.username,
                list_name=shopping_list.name,
                accept_url=accept_url,
                reject_url=reject_url,
            )

        expires_at = datetime.now(timezone.utc) + expires_delta
        return expires_at

    async def accept_invitation(
        self, token: str, user: User
    ) -> ShoppingList:
        """
        Accept an invitation to join a shopping list.
        
        Args:
            token: Invitation JWT token
            user: Accepting user (must be logged in)
        
        Returns:
            ShoppingList: The list the user just joined
        
        Raises:
            ValidationException: If token is invalid or expired
            ForbiddenException: If email mismatch or cross-tenant
            ConflictException: If already a member
        """
        # Decode token
        try:
            payload = decode_invitation_token(token)
        except JWTError as e:
            raise ValidationException(f"Invalid or expired invitation token: {str(e)}")

        # Validate token type
        if payload.get("type") != "list_invite":
            raise ValidationException("Invalid token type")

        # Validate email matches
        if payload["email"] != user.email:
            raise ForbiddenException(
                "This invitation was sent to a different email address"
            )

        # Validate tenant matches
        if UUID(payload["tenant_id"]) != user.tenant_id:
            raise ForbiddenException("Cross-tenant invitation not allowed")

        # Check token exists in Redis (one-time use)
        token_id = payload["jti"]
        stored_list_id = await RedisService.validate_invitation_token(token_id)

        if not stored_list_id:
            raise ValidationException(
                "Invitation has already been used or has expired"
            )

        list_id = UUID(payload["list_id"])

        # Verify list still exists
        result = await self.db.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        shopping_list = result.scalar_one_or_none()

        if not shopping_list:
            # Clean up token
            await RedisService.invalidate_invitation_token(token_id)
            raise NotFoundException("Shopping list no longer exists")

        # Check if already a member
        result = await self.db.execute(
            select(ShoppingListMember).where(
                and_(
                    ShoppingListMember.shopping_list_id == list_id,
                    ShoppingListMember.user_id == user.id,
                )
            )
        )
        if result.scalar_one_or_none():
            # Clean up token
            await RedisService.invalidate_invitation_token(token_id)
            raise ConflictException("You are already a member of this list")

        # Create membership
        membership = ShoppingListMember(
            shopping_list_id=list_id,
            user_id=user.id,
            role=MemberRole.MEMBER,
        )
        self.db.add(membership)
        await self.db.commit()

        # Invalidate token (one-time use)
        await RedisService.invalidate_invitation_token(token_id)

        # Publish event for real-time update
        await RedisService.publish_event(
            f"list:{list_id}",
            json.dumps({
                "event": "member_joined",
                "list_id": str(list_id),
                "data": {
                    "user_id": str(user.id),
                    "username": user.username,
                    "role": MemberRole.MEMBER.value,
                },
            }),
        )

        await self.db.refresh(shopping_list)
        return shopping_list

    async def reject_invitation(self, token: str) -> bool:
        """
        Reject an invitation.
        
        Args:
            token: Invitation JWT token
        
        Returns:
            bool: True (always succeeds)
        
        Note:
            No database changes occur. Token is simply invalidated if valid.
        """
        try:
            payload = decode_invitation_token(token)
            token_id = payload.get("jti")
            if token_id:
                # Invalidate token if it exists
                await RedisService.invalidate_invitation_token(token_id)
        except JWTError:
            # Invalid token, just ignore
            pass

        return True
