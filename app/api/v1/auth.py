"""
Authentication Endpoints

Handles login, logout, email verification, token refresh,
forgot/reset password, and change password.
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_user, get_tenant_id
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    ResendOtpRequest,
    RefreshTokenRequest,
    VerifyEmailRequest,
    OTPResponse,
    SignupRequest,
    SignupResponse,
    LogoutRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from app.schemas.user import ChangePasswordRequest
from app.core.config import settings
from sqlalchemy import select
from app.models.tenant import Tenant
from app.schemas.common import MessageResponse
from app.models.user import User
from app.services.auth_service import AuthService
from app.exceptions import ValidationException


router = APIRouter()
security = HTTPBearer(auto_error=True)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[Optional[UUID], Depends(get_tenant_id)] = None,
):
    """
    Authenticate user and return JWT tokens.
    """
    auth_service = AuthService(db)
    return await auth_service.login(
        **data.model_dump(), tenant_id=tenant_id, background_tasks=background_tasks
    )


@router.post(
    "/signup",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup(
    data: SignupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[UUID, Depends(get_tenant_id)],
):
    """
    Register a new user account.
    """
    if not tenant_id:
        from app.exceptions import ValidationException

        raise ValidationException("Tenant-ID header is required for signup")

    auth_service = AuthService(db)
    await auth_service.signup(
        **data.model_dump(),
        tenant_id=tenant_id,
        background_tasks=background_tasks,
    )
    return MessageResponse(message="Signup successful. Please verify your email.")


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def logout(
    data: LogoutRequest,
    current_user: Annotated["User", Depends(get_current_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Logout user by blacklisting both access and refresh tokens.
    """
    auth_service = AuthService(db)
    access_token = credentials.credentials
    await auth_service.logout(access_token, data.refresh_token)
    return MessageResponse(message="Logged out successfully")


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def verify_email(
    data: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[UUID, Depends(get_tenant_id)],
):
    """
    Verify email address using OTP.
    """
    if not tenant_id:
        raise ValidationException("Tenant-ID header is required")

    auth_service = AuthService(db)
    await auth_service.verify_email(**data.model_dump(), tenant_id=tenant_id)
    return MessageResponse(message="Email verified successfully")


@router.post(
    "/resend-otp",
    response_model=OTPResponse,
    status_code=status.HTTP_200_OK,
)
async def resend_otp(
    data: ResendOtpRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[UUID, Depends(get_tenant_id)],
):
    """
    Resend OTP for email verification.
    """
    if not tenant_id:
        raise ValidationException("Tenant-ID header is required ")

    auth_service = AuthService(db)
    await auth_service.send_verification_otp(data.email, tenant_id, background_tasks)
    return OTPResponse(
        message="OTP sent successfully",
        expires_in=settings.otp_expire_minutes * 60,
    )


@router.post(
    "/refresh",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh_tokens(
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Refresh access and refresh tokens.
    """
    auth_service = AuthService(db)
    access_token, refresh_token = await auth_service.refresh_tokens(data.refresh_token)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Change current user's password.
    Requires authentication.
    """
    auth_service = AuthService(db)
    await auth_service.change_password(
        current_user, data.current_password, data.new_password
    )
    return MessageResponse(message="Password changed successfully")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def forgot_password(
    data: PasswordResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[Optional[UUID], Depends(get_tenant_id)] = None,
):
    """
    Request a password reset link via email.
    Always returns success to prevent email enumeration.
    """
    auth_service = AuthService(db)
    await auth_service.forgot_password(data.email, tenant_id, background_tasks)
    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_password(
    data: PasswordResetConfirm,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Reset password using a valid reset token.
    Token is single-use and expires in 15 minutes.
    """
    auth_service = AuthService(db)
    await auth_service.reset_password(
        data.token, data.new_password, data.confirm_password
    )
    return MessageResponse(message="Password has been reset successfully")
