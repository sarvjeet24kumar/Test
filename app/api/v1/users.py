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
from app.core.responses import success_response
from app.exceptions import ForbiddenException
from app.models.user import User
from app.common.enums import UserRole
from app.services.user_service import UserService
from math import ceil
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.schemas.common import ResponseEnvelope, PaginatedResponse, MessageResponse

router = APIRouter()


@router.post(
    "",
    response_model=ResponseEnvelope[UserResponse],
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
    """
    user_service = UserService(db)
    
    if current_user.role == UserRole.SUPER_ADMIN:
        user = await user_service.create_user(
            data=data,
            role=UserRole.TENANT_ADMIN,
            background_tasks=background_tasks,
        )
    elif current_user.role == UserRole.TENANT_ADMIN:
        user = await user_service.create_user(
            data=data,
            tenant_id=current_user.tenant_id,
            role=UserRole.USER,
            background_tasks=background_tasks,
        )
    else:
        raise ForbiddenException("Only Admins can create users")
    
    return success_response({
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "is_active": user.is_active,
        "is_email_verified": user.is_email_verified,
        "tenant_id": user.tenant_id,
        "created_at": user.created_at,
    })


@router.get(
    "",
    response_model=ResponseEnvelope[PaginatedResponse[UserResponse]],
    status_code=status.HTTP_200_OK,
)
async def list_users(
    current_user: Annotated[User, Depends(require_role(UserRole.TENANT_ADMIN, UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
):
    """
    List users based on role.
    """
    user_service = UserService(db)
    
    if current_user.role == UserRole.SUPER_ADMIN:
        items, total = await user_service.get_users_in_tenant(
            skip=pagination.skip,
            limit=pagination.size
        )
    else:
        items, total = await user_service.get_users_in_tenant(
            tenant_id=current_user.tenant_id,
            skip=pagination.skip,
            limit=pagination.size
        )
    
    
    return success_response({
        "items": items,
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if total > 0 else 1,
    })


@router.get(
    "/{user_id}",
    response_model=ResponseEnvelope[UserResponse],
    status_code=status.HTTP_200_OK,
)
async def get_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get a specific user.
    """
    user_service = UserService(db)
    user = await user_service.get_user(user_id, current_user)
    return success_response({
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role.value,
        "is_active": user.is_active,
        "is_email_verified": user.is_email_verified,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "created_at": user.created_at.isoformat(),
        "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
    })


@router.patch(
    "/{user_id}",
    response_model=ResponseEnvelope[UserResponse],
    status_code=status.HTTP_200_OK,
)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a user.
    """
    user_service = UserService(db)
    user = await user_service.update_user(user_id, current_user, data)
    return success_response({
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role.value,
        "is_active": user.is_active,
        "is_email_verified": user.is_email_verified,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "created_at": user.created_at.isoformat(),
        "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
    })


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Deactivate a user (soft delete).
    """
    user_service = UserService(db)
    return await user_service.deactivate_user(user_id, current_user)


@router.post(
    "/{user_id}/resend-otp",
    response_model=ResponseEnvelope[MessageResponse],
    status_code=status.HTTP_200_OK,
)
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
    return success_response({"message": "OTP sent successfully"})
