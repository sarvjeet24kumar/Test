"""
Authentication Endpoints

Handles login, logout, email verification, and token refresh.
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_user, get_tenant_id
from app.models.user import User, UserRole
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
)
from app.schemas.user import ChangePasswordRequest

router = APIRouter()
security = HTTPBearer(auto_error=True)



@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[Optional[UUID], Depends(get_tenant_id)] = None,
):
    """
    Authenticate user and return JWT tokens.
    
    - **email**: User's email address
    - **password**: User's password
    
    Returns access and refresh tokens on success.
    """
    auth_service = AuthService(db)
    return await auth_service.login(data.email, data.password, tenant_id, background_tasks)


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    data: SignupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[Optional[UUID], Depends(get_tenant_id)] = None,
):
    """
    Register a new user account.
    
    - **email**: User's email address
    - **username**: Desired username (alphanumeric and underscore)
    - **first_name**: User's first name
    - **last_name**: User's last name
    - **password**: Password (minimum 8 characters)
    
    Creates user with `is_email_verified=False` and sends verification email.
    Requires `Tenant-ID` header.
    """
    print(tenant_id)
    auth_service = AuthService(db)
    return await auth_service.signup(
        email=data.email,
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
        password=data.password,
        tenant_id=tenant_id,
        background_tasks=background_tasks,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    data: LogoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Logout user by blacklisting both access and refresh tokens.
    
    - **refresh_token**: User's current refresh token
    
    Requires authentication. Access token is extracted from Authorization header.
    Both tokens will be blacklisted and cannot be used again.
    """
    from fastapi.security import HTTPBearer
    
    auth_service = AuthService(db)
    # Extract access token from Authorization header
    access_token = credentials.credentials
    await auth_service.logout(access_token, data.refresh_token)
    return {"message": "Logged out successfully"}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(
    data: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[Optional[UUID], Depends(get_tenant_id)] = None,
):
    """
    Verify email address using OTP.
    
    - **email**: User's email address
    - **otp**: 6-digit OTP code received via email
    """
    auth_service = AuthService(db)
    await auth_service.verify_email(data.email, data.otp, tenant_id)
    return {"message": "Email verified successfully"}


@router.post("/resend-otp", response_model=OTPResponse)
async def resend_otp(
    data: ResendOtpRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[Optional[UUID], Depends(get_tenant_id)] = None,
):
    """
    Resend OTP for email verification.
    
    - **email**: User's email address
    """
    auth_service = AuthService(db)
    await auth_service.send_verification_otp(data.email, tenant_id, background_tasks)
    from app.core.config import settings
    return OTPResponse(expires_in=settings.otp_expire_minutes * 60)


@router.post("/refresh", response_model=LoginResponse)
async def refresh_tokens(
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Refresh access and refresh tokens.z
    
    - **refresh_token**: Current refresh token
    """
    auth_service = AuthService(db)
    access_token, refresh_token = await auth_service.refresh_tokens(data.refresh_token)
    from app.core.config import settings
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/change-password", status_code=status.HTTP_200_OK)
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
    return {"message": "Password changed successfully"}


@router.get("/me")
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
    
    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "tenant_id": current_user.tenant_id,
        "tenant_name": tenant_name,
        "role": current_user.role,
        "is_email_verified": current_user.is_email_verified,
        "created_at": current_user.created_at,
    }
