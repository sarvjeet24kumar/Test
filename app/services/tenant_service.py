"""
Tenant Service

Handles tenant creation and management (Super Admin operations).
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.security import hash_password, generate_otp
from app.exceptions import NotFoundException, ConflictException
from app.models.tenant import Tenant
from app.models.user import User
from app.common.enums import UserRole
from app.schemas.tenant import TenantCreate, TenantUpdate
from app.services.redis_service import RedisService
from app.services.email_service import EmailService
from app.core.config import settings


class TenantService:
    """Service for tenant management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tenant(self, data: TenantCreate) -> Tenant:
        """
        Create a new tenant.

        Args:
            data: Tenant creation data

        Returns:
            Created Tenant
        """
        # Check for existing slug
        result = await self.db.execute(select(Tenant).where(Tenant.slug == data.slug))
        if result.scalar_one_or_none():
            raise ConflictException(f"Slug already exists")

        tenant = Tenant(
            name=data.name,
            slug=data.slug,
            is_active=True,
        )
        self.db.add(tenant)
        await self.db.commit()
        await self.db.refresh(tenant)
        return tenant

    async def get_tenant(self, tenant_id: UUID) -> Tenant:
        """
        Get a tenant by ID.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Tenant

        Raises:
            NotFoundException: If tenant not found
        """
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()

        if not tenant:
            raise NotFoundException("Tenant not found")

        return tenant

    async def get_all_tenants(
        self, skip: int = 0, limit: int = 100
    ) -> tuple[List[Tenant], int]:
        """
        Get all tenants with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (List of Tenants, Total Count)
        """
        # Get total count
        count_result = await self.db.execute(select(func.count()).select_from(Tenant))
        total = count_result.scalar_one()

        # Get paginated items
        result = await self.db.execute(select(Tenant).offset(skip).limit(limit))
        items = list(result.scalars().all())

        return items, total

    async def update_tenant(self, tenant_id: UUID, data: TenantUpdate) -> Tenant:
        tenant = await self.get_tenant(tenant_id)

        update_data = data.model_dump(exclude_unset=True)

        # Special validation for slug
        if "slug" in update_data and update_data["slug"] != tenant.slug:
            result = await self.db.execute(
                select(Tenant).where(Tenant.slug == update_data["slug"])
            )
            if result.scalar_one_or_none():
                raise ConflictException(f"Slug already exists")

        for field, value in update_data.items():
            setattr(tenant, field, value)

        await self.db.commit()
        await self.db.refresh(tenant)
        return tenant

    async def delete_tenant(self, tenant_id: UUID) -> Tenant:
        """
        Soft delete a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Deleted Tenant

        Raises:
            NotFoundException: If tenant not found
            ConflictException: If tenant already deleted
        """
        tenant = await self.get_tenant(tenant_id)
        if tenant.deleted_at:
            raise ConflictException("Tenant already deleted")

        tenant.deleted_at = func.now()
        tenant.is_active = False
        await self.db.commit()
        await self.db.refresh(tenant)
        return tenant
