"""
Tenant Management Endpoints

Super Admin only operations for tenant management.
"""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import require_role, PaginationParams
from app.core.responses import success_response
from app.models.user import User
from app.common.enums import UserRole
from app.services.tenant_service import TenantService
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse
from app.schemas.common import ResponseEnvelope, PaginatedResponse
from math import ceil

router = APIRouter()


@router.post(
    "",
    response_model=ResponseEnvelope[TenantResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant(
    data: TenantCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new tenant.
    **Super Admin only.**
    """
    tenant_service = TenantService(db)
    tenant = await tenant_service.create_tenant(data)
    return success_response(tenant)


@router.get(
    "",
    response_model=ResponseEnvelope[PaginatedResponse[TenantResponse]],
    status_code=status.HTTP_200_OK,
)
async def list_tenants(
    current_user: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
):
    """
    List all tenants.
    **Super Admin only.**
    """
    tenant_service = TenantService(db)
    items, total = await tenant_service.get_all_tenants(
        skip=pagination.skip, limit=pagination.size
    )
    
    return success_response({
        "items": items,
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if total > 0 else 1,
    })


@router.get(
    "/{tenant_id}",
    response_model=ResponseEnvelope[TenantResponse],
    status_code=status.HTTP_200_OK,
)
async def get_tenant(
    tenant_id: UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get a specific tenant.
    **Super Admin only.**
    """
    tenant_service = TenantService(db)
    tenant = await tenant_service.get_tenant(tenant_id)
    return success_response({
        "id": str(tenant.id),
        "name": tenant.name,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat(),
        "updated_at": tenant.updated_at.isoformat(),
    })


@router.patch(
    "/{tenant_id}",
    response_model=ResponseEnvelope[TenantResponse],
    status_code=status.HTTP_200_OK,
)
async def update_tenant(
    tenant_id: UUID,
    data: TenantUpdate,
    current_user: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a tenant.
    **Super Admin only.**
    """
    tenant_service = TenantService(db)
    tenant = await tenant_service.update_tenant(tenant_id, data)
    return success_response(tenant)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Soft delete a tenant.
    **Super Admin only.**
    """
    tenant_service = TenantService(db)
    await tenant_service.delete_tenant(tenant_id)
