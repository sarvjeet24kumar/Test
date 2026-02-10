"""
Authentication Service

Handles user authentication, login, and email verification.
"""

from datetime import timedelta
from typing import Tuple, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_password,
)
from app.exceptions import (
    UnauthorizedException,
    ForbiddenException,
    TenantInactiveException,
    EmailNotVerifiedException,
    NotFoundException,
    ValidationException,
)
from app.models.user import User
from app.models.tenant import Tenant
from app.services.redis_service import RedisService
from app.services.email_service import EmailService
from app.schemas.auth import LoginResponse


from fastapi import BackgroundTasks

class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def login(
        self, 
        email: str, 
        password: str, 
        tenant_id: Optional[UUID] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> LoginResponse:
        """
        Authenticate user and return tokens.
        
        Args:
            email: User's email
            password: User's password
            tenant_id: Tenant UUID (None for SuperAdmin)
            background_tasks: Background tasks handler
        
        Returns:
            LoginResponse with access and refresh tokens
        
        Raises:
            UnauthorizedException: If credentials are invalid
            ForbiddenException: If user is inactive
            TenantInactiveException: If tenant is inactive
            EmailNotVerifiedException: If email not verified
        """
        # Find user by email and tenant
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.email == email,
                    User.tenant_id == tenant_id
                )
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UnauthorizedException("Invalid email or password")

        # Verify password
        if not verify_password(password, user.password):
            raise UnauthorizedException("Invalid email or password")

        # Check user status
        if not user.is_active:
            raise ForbiddenException("User account is inactive")

        # Check email verification
        if not user.is_email_verified:
            # Send new OTP
            await self.send_verification_otp(email, tenant_id, background_tasks)
            raise EmailNotVerifiedException(
                "Please verify your email before logging in. A new OTP has been sent."
            )

        # Check tenant status if associated
        if user.tenant_id:
            result = await self.db.execute(
                select(Tenant).where(Tenant.id == user.tenant_id)
            )
            tenant = result.scalar_one_or_none()

            if not tenant or not tenant.is_active:
                raise TenantInactiveException()

        # Generate tokens
        access_token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role.value,
            email=user.email,
        )
        refresh_token = create_refresh_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
        )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )

    async def send_verification_otp(
        self, 
        email: str, 
        tenant_id: Optional[UUID] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """
        Send OTP for email verification scoped by tenant.
        """
        # Verify user exists in this tenant context
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.email == email,
                    User.tenant_id == tenant_id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise NotFoundException("User not found in this tenant context")

        # Generate OTP
        otp = generate_otp()

        # Store in Redis
        expire_seconds = settings.otp_expire_minutes * 60
        await RedisService.store_otp(email, otp, expire_seconds)

        # Send email
        if background_tasks:
            background_tasks.add_task(EmailService.send_otp_email, email, otp)
        else:
            await EmailService.send_otp_email(email, otp)

    async def verify_email(
        self, email: str, otp: str, tenant_id: Optional[UUID] = None
    ) -> bool:
        """
        Verify email with OTP scoped by tenant.
        
        Args:
            email: User's email
            otp: OTP code
            tenant_id: Optional tenant UUID
        
        Returns:
            bool: True if verified successfully
        
        Raises:
            ValidationException: If OTP is invalid or expired
        """
        # Get stored OTP
        stored_otp = await RedisService.get_otp(email)

        if not stored_otp:
            raise ValidationException("OTP has expired. Please request a new one.")

        if stored_otp != otp:
            raise ValidationException("Invalid OTP")

        # Update user's email verification status
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.email == email,
                    User.tenant_id == tenant_id
                )
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            raise NotFoundException("User not found")

        user.is_email_verified = True
        await self.db.commit()

        # Delete OTP from Redis
        await RedisService.delete_otp(email)

        return True

    async def refresh_tokens(
        self, refresh_token: str
    ) -> Tuple[str, str]:
        """
        Refresh access and refresh tokens.
        
        Args:
            refresh_token: Current refresh token
        
        Returns:
            Tuple of (new_access_token, new_refresh_token)
        
        Raises:
            UnauthorizedException: If refresh token is invalid
        """
        from jose import jwt, JWTError

        try:
            payload = jwt.decode(
                refresh_token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError:
            raise UnauthorizedException("Invalid refresh token")

        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid token type")

        # Check if token is blacklisted
        token_id = payload.get("jti")
        if await RedisService.is_token_blacklisted(token_id):
            raise UnauthorizedException("Token has been revoked")

        # Get user
        user_id = payload.get("sub")
        result = await self.db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise UnauthorizedException("User not found or inactive")

        # Blacklist old refresh token
        # Calculate remaining TTL (but use a minimum of 1 day for safety)
        await RedisService.blacklist_token(token_id, 60 * 60 * 24)

        # Generate new tokens
        access_token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role.value,
            email=user.email,
        )
        new_refresh_token = create_refresh_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
        )

        return access_token, new_refresh_token

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> bool:
        """
        Change user's password.
        
        Args:
            user: Current user
            current_password: Current password
            new_password: New password
        
        Returns:
            bool: True if changed successfully
        
        Raises:
            ValidationException: If current password is incorrect
        """
        if not verify_password(current_password, user.password):
            raise ValidationException("Current password is incorrect")

        user.password = hash_password(new_password)
        await self.db.commit()

        return True
