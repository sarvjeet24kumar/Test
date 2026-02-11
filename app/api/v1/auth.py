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
from app.core.responses import success_response
from app.models.user import User
from app.services.auth_service import AuthService
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
from app.schemas.user import ChangePasswordRequest, UserProfileResponse
from app.schemas.common import ResponseEnvelope, MessageResponse

router = APIRouter()
security = HTTPBearer(auto_error=True)


@router.post(
    "/login",
    response_model=ResponseEnvelope[LoginResponse],
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
    result = await auth_service.login(data.email, data.password, tenant_id, background_tasks)
    return success_response({
        "access_token": result.access_token,
        "refresh_token": result.refresh_token,
        "token_type": result.token_type,
        "expires_in": result.expires_in,
    })


@router.post(
    "/signup",
    response_model=ResponseEnvelope[SignupResponse],
    status_code=status.HTTP_201_CREATED,
)
async def signup(
    data: SignupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[Optional[UUID], Depends(get_tenant_id)] = None,
):
    """
    Register a new user account.
    """
    auth_service = AuthService(db)
    result = await auth_service.signup(
        email=data.email,
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
        password=data.password,
        tenant_id=tenant_id,
        background_tasks=background_tasks,
    )
    return success_response({
        "message": result.message,
        "user_id": result.user_id,
        "email": result.email,
        "is_email_verified": result.is_email_verified,
    })


@router.post(
    "/logout",
    response_model=ResponseEnvelope[MessageResponse],
    status_code=status.HTTP_200_OK,
)
async def logout(
    data: LogoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Logout user by blacklisting both access and refresh tokens.
    """
    auth_service = AuthService(db)
    access_token = credentials.credentials
    await auth_service.logout(access_token, data.refresh_token)
    return success_response({"message": "Logged out successfully"})


@router.post(
    "/verify-email",
    response_model=ResponseEnvelope[MessageResponse],
    status_code=status.HTTP_200_OK,
)
async def verify_email(
    data: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[Optional[UUID], Depends(get_tenant_id)] = None,
):
    """
    Verify email address using OTP.
    """
    auth_service = AuthService(db)
    await auth_service.verify_email(data.email, data.otp, tenant_id)
    return success_response({"message": "Email verified successfully"})


@router.post(
    "/resend-otp",
    response_model=ResponseEnvelope[OTPResponse],
    status_code=status.HTTP_200_OK,
)
async def resend_otp(
    data: ResendOtpRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[Optional[UUID], Depends(get_tenant_id)] = None,
):
    """
    Resend OTP for email verification.
    """
    auth_service = AuthService(db)
    await auth_service.send_verification_otp(data.email, tenant_id, background_tasks)
    from app.core.config import settings
    return success_response({
        "message": "OTP sent successfully",
        "expires_in": settings.otp_expire_minutes * 60,
    })


@router.post(
    "/refresh",
    response_model=ResponseEnvelope[LoginResponse],
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
    from app.core.config import settings
    return success_response({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
    })


@router.post(
    "/change-password",
    response_model=ResponseEnvelope[MessageResponse],
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
    return success_response({"message": "Password changed successfully"})


@router.post(
    "/forgot-password",
    response_model=ResponseEnvelope[MessageResponse],
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
    return success_response({
        "message": "If an account with that email exists, a password reset link has been sent."
    })


@router.post(
    "/reset-password",
    response_model=ResponseEnvelope[MessageResponse],
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
    await auth_service.reset_password(data.token, data.new_password, data.confirm_password)
    return success_response({"message": "Password has been reset successfully"})


@router.get(
    "/me",
    response_model=ResponseEnvelope[UserProfileResponse],
    status_code=status.HTTP_200_OK,
)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get current user's profile.
    Requires authentication.
    """
    from sqlalchemy import select
    from app.models.tenant import Tenant
    
    tenant_name = "Global"
    if current_user.tenant_id:
        result = await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant:
            tenant_name = tenant.name
        else:
            tenant_name = "Deleted Tenant"
    
    return success_response({
        "id": str(current_user.id),
        "email": current_user.email,
        "username": current_user.username,
        "tenant_id": str(current_user.tenant_id) if current_user.tenant_id else None,
        "tenant_name": tenant_name,
        "role": current_user.role.value,
        "is_email_verified": current_user.is_email_verified,
        "created_at": current_user.created_at.isoformat(),
    })
