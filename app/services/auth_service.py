"""
Authentication Service

Handles user authentication, login, signup, email verification,
password reset, and password changes.
"""

import hmac
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from uuid import UUID

from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    create_password_reset_token,
    decode_password_reset_token,
    generate_otp,
    hash_password,
    decode_token,
)
from app.exceptions import (
    UnauthorizedException,
    ForbiddenException,
    TenantInactiveException,
    EmailNotVerifiedException,
    NotFoundException,
    ValidationException,
    ConflictException,
)
from app.exceptions.base import MiniMartException
from app.models.user import User
from app.models.tenant import Tenant
from app.models.token_blacklist import BlacklistedToken
from app.services.redis_service import RedisService
from app.services.email_service import EmailService
from app.schemas.auth import LoginResponse, SignupResponse
from app.utils.password import validate_password_strength
from app.common.enums import UserRole
from app.core.logging import get_logger

logger = get_logger(__name__)



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
        
        Silent fail if user not found (prevents email enumeration).
        Raises ALREADY_VERIFIED if user is already verified.
        """
        # Find user by email and tenant
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.email == email,
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                )
            )
        )
        user = result.scalar_one_or_none()

        # Silent fail — prevent email enumeration
        if not user:
            return

        # Block if already verified
        if user.is_email_verified:
            raise MiniMartException(
                status_code=400,
                code="ALREADY_VERIFIED",
                message="Account is already verified.",
            )

        # Generate OTP
        otp = generate_otp()

        # Store in Redis
        expire_seconds = settings.otp_expire_minutes * 60
        await RedisService.store_otp(email, otp, expire_seconds, tenant_id)

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
        Uses constant-time comparison for OTP.
        Raises ALREADY_VERIFIED if user is already verified.
        """
        # Find user
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

        # Block if already verified
        if user.is_email_verified:
            raise MiniMartException(
                status_code=400,
                code="ALREADY_VERIFIED",
                message="Account is already verified.",
            )

        # Get stored OTP
        stored_otp = await RedisService.get_otp(email, tenant_id)

        if not stored_otp:
            raise ValidationException("OTP has expired. Please request a new one.")

        # Constant-time comparison
        if not hmac.compare_digest(stored_otp, otp):
            raise ValidationException("Invalid OTP")

        # Update user's email verification status
        user.is_email_verified = True
        await self.db.commit()

        # Delete OTP from Redis
        await RedisService.delete_otp(email, tenant_id)

        return True

    async def signup(
        self,
        email: str,
        username: str,
        first_name: str,
        last_name: str,
        password: str,
        tenant_id: Optional[UUID] = None,
        background_tasks: Optional["BackgroundTasks"] = None,
    ) -> SignupResponse:
        """
        Register a new user with email verification.
        """
        # Validate password strength
        validate_password_strength(password)

        # Verify tenant exists if tenant_id provided
        if tenant_id:
            result = await self.db.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = result.scalar_one_or_none()
            if not tenant:
                raise NotFoundException("Tenant not found")
            if not tenant.is_active:
                raise TenantInactiveException()

        # Check if email already exists in this tenant
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.email == email,
                    User.tenant_id == tenant_id
                )
            )
        )
        if result.scalar_one_or_none():
            raise ConflictException("Email already registered in this tenant")

        # Check if username already exists in this tenant
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.username == username,
                    User.tenant_id == tenant_id
                )
            )
        )
        if result.scalar_one_or_none():
            raise ConflictException("Username already taken in this tenant")

        # Create user with is_email_verified=False
        user = User(
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=hash_password(password),
            tenant_id=tenant_id,
            role=UserRole.USER,
            is_email_verified=False,
            is_active=True,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        # Send verification email
        await self.send_verification_otp(email, tenant_id, background_tasks)

        return SignupResponse(
            user_id=user.id,
            email=user.email,
            is_email_verified=user.is_email_verified,
        )

    async def logout(
        self,
        access_token: str,
        refresh_token: str,
    ) -> None:
        """
        Logout user by blacklisting both access and refresh tokens.
        """
        # Decode and validate access token
        try:
            access_payload = decode_token(access_token)
        except JWTError:
            raise UnauthorizedException("Invalid access token")

        # Decode and validate refresh token
        try:
            refresh_payload = decode_token(refresh_token)
        except JWTError:
            raise UnauthorizedException("Invalid refresh token")

        # Blacklist access token in Redis (short-lived, fast lookup)
        access_jti = access_payload.get("jti")
        access_exp = access_payload.get("exp")
        if access_jti and access_exp:
            ttl = int(access_exp - datetime.now(timezone.utc).timestamp())
            if ttl > 0:
                await RedisService.blacklist_access_token(access_jti, ttl)

        # Blacklist refresh token in database (long-lived, persistent)
        refresh_jti = refresh_payload.get("jti")
        refresh_exp = refresh_payload.get("exp")
        user_id = refresh_payload.get("sub")
        
        if refresh_jti and refresh_exp:
            result = await self.db.execute(
                select(BlacklistedToken).where(
                    BlacklistedToken.token_id == refresh_jti
                )
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                expires_at = datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc)
                
                blacklisted = BlacklistedToken(
                    token_id=refresh_jti,
                    user_id=user_id,
                    expires_at=expires_at,
                )
                self.db.add(blacklisted)
                await self.db.commit()

        # Proactive Security: Immediately close all active WebSocket connections for this user
        from app.websocket.manager import manager
        await manager.disconnect_all_for_user(str(user_id))

    async def refresh_tokens(self, refresh_token: str) -> Tuple[str, str]:
        from jose import jwt
        from uuid import UUID as UUIDType

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

        # Check if refresh token is blacklisted
        token_id = payload.get("jti")
        result = await self.db.execute(
            select(BlacklistedToken).where(BlacklistedToken.token_id == token_id)
        )
        if result.scalar_one_or_none():
            raise UnauthorizedException("Token has been revoked")

        # Get user
        user_id = payload.get("sub")
        result = await self.db.execute(select(User).where(User.id == UUIDType(user_id)))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise UnauthorizedException("User not found or inactive")

        # Generate new access token
        access_token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role.value,
            email=user.email,
        )

        # Return the same refresh token
        return access_token, refresh_token

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> bool:
        """
        Change user's password with strength validation.
        Ensures new password != current password.
        """
        if not verify_password(current_password, user.password):
            raise ValidationException("Current password is incorrect")

        # Check new password is not same as current
        if verify_password(new_password, user.password):
            raise MiniMartException(
                status_code=400,
                code="PASSWORD_SAME",
                message="New password must be different from your current password.",
            )

        # Validate new password strength
        validate_password_strength(new_password)

        user.password = hash_password(new_password)
        await self.db.commit()

        return True

    async def forgot_password(
        self,
        email: str,
        tenant_id: Optional[UUID] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """
        Request password reset. Sends email with reset link.
        Silent fail if user not found (prevent email enumeration).
        """
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.email == email,
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                )
            )
        )
        user = result.scalar_one_or_none()

        # Silent fail — prevent email enumeration
        if not user:
            return

        # Generate reset token (JWT with jti)
        token = create_password_reset_token(user.id, user.tenant_id)

        # Decode to get the jti
        payload = decode_token(token)
        jti = payload.get("jti")

        # Store jti in Redis for single-use validation (15 min)
        await RedisService.store_password_reset_jti(jti, str(user.id), 900)

        # Build reset URL
        reset_url = f"{settings.invitation_base_url.rsplit('/', 1)[0]}/reset-password?token={token}"

        # Send email
        if background_tasks:
            background_tasks.add_task(
                EmailService.send_password_reset_email, user.email, reset_url
            )
        else:
            await EmailService.send_password_reset_email(user.email, reset_url)

    async def reset_password(
        self, token: str, new_password: str, confirm_password: str
    ) -> bool:
        """
        Reset password using a valid reset token.
        Token is single-use (jti tracked in Redis).
        """
        # Validate passwords match
        if new_password != confirm_password:
            raise MiniMartException(
                status_code=400,
                code="PASSWORD_MISMATCH",
                message="Passwords do not match.",
                details={"confirm_password": ["Must match new_password."]},
            )

        # Validate password strength
        validate_password_strength(new_password)

        # Decode token
        try:
            payload = decode_password_reset_token(token)
        except JWTError:
            raise MiniMartException(
                status_code=400,
                code="INVALID_RESET_TOKEN",
                message="Password reset token is invalid or has expired.",
            )

        jti = payload.get("jti")
        user_id = payload.get("sub")

        # Check jti exists in Redis (single-use)
        stored_user_id = await RedisService.validate_password_reset_jti(jti)
        if not stored_user_id:
            raise MiniMartException(
                status_code=400,
                code="INVALID_RESET_TOKEN",
                message="Password reset token has already been used or has expired.",
            )

        # Get user
        result = await self.db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()

        if not user:
            raise NotFoundException("User not found")

        # Hash & update password
        user.password = hash_password(new_password)
        await self.db.commit()

        # Delete jti from Redis (single-use)
        await RedisService.delete_password_reset_jti(jti)

        return True
