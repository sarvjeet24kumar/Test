"""
User Management Endpoints

Tenant Admin operations for user management within a tenant.
"""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import require_role, get_current_verified_user, PaginationParams
from app.exceptions import ForbiddenException
from app.models.user import User, UserRole
from app.services.user_service import UserService
from math import ceil
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserUpdate, UserResponse

router = APIRouter()


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    data: UserCreate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """
    Create a new user.
    
    - **Super Admin**: Can create a `TENANT_ADMIN` in any tenant (specified in payload).
    - **Tenant Admin**: Can only create a `USER` in their own tenant.
    """
    user_service = UserService(db)
    
    if current_user.role == UserRole.SUPER_ADMIN:
        # Super Admin creates Tenant Admin by default
        return await user_service.create_user(
            data=data,
            role=UserRole.TENANT_ADMIN,
            background_tasks=background_tasks,
        )
    elif current_user.role == UserRole.TENANT_ADMIN:
        # Tenant Admin can only create USER in their own tenant
        return await user_service.create_user(
            data=data,
            tenant_id=current_user.tenant_id,
            role=UserRole.USER,
            background_tasks=background_tasks,
        )
    else:
        raise ForbiddenException("Only Admins can create users")


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    current_user: Annotated[User, Depends(require_role(UserRole.TENANT_ADMIN, UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
):
    """
    List users based on role.
    
    - **Super Admin**: Sees all `TENANT_ADMIN` users (all tenants, including deleted).
    - **Tenant Admin**: Sees all users in their own tenant.
    """
    user_service = UserService(db)
    
    if current_user.role == UserRole.SUPER_ADMIN:
        # Super Admin sees global view (Tenant Admins + deleted)
        items, total = await user_service.get_users_in_tenant(
            skip=pagination.skip,
            limit=pagination.size
        )
    else:
        # Tenant Admin sees all users in their tenant
        items, total = await user_service.get_users_in_tenant(
            tenant_id=current_user.tenant_id,
            skip=pagination.skip,
            limit=pagination.size
        )
    
    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=ceil(total / pagination.size) if total > 0 else 1,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get a specific user.
    
    Access:
    - **Self**: Any user can see their own profile.
    - **Super Admin**: Can see Tenant Admins globally.
    - **Tenant Admin**: Can see users in their specific tenant.
    """
    user_service = UserService(db)
    return await user_service.get_user(user_id, current_user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a user.
    
    Access:
    - **Self**: Update names/username (email update blocked).
    - **Super Admin**: Manage Tenant Admins globally.
    - **Tenant Admin**: Manage users in their tenant.
    """
    user_service = UserService(db)
    return await user_service.update_user(user_id, current_user, data)


@router.delete("/{user_id}", response_model=UserResponse)
async def deactivate_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Deactivate a user (soft delete).
    
    Access:
    - **Self**: Any user can deactivate their own account.
    - **Super Admin**: Can deactivate global Tenant Admins.
    - **Tenant Admin**: Can deactivate users in their tenant.
    """
    user_service = UserService(db)
    return await user_service.deactivate_user(user_id, current_user)


@router.post("/{user_id}/resend-otp", status_code=status.HTTP_200_OK)
async def resend_user_otp(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """
    Resend verification OTP to a user.
    """
    user_service = UserService(db)
    await user_service.resend_verification_otp(user_id, current_user, background_tasks)
    return {"message": "OTP sent successfully"}
