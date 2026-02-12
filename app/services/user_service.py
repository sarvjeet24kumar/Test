"""
User Service

Handles user management within a tenant (Tenant Admin operations).
"""

from typing import List, Optional
from uuid import UUID
from fastapi import Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import update


from app.core.security import hash_password, generate_otp
from app.exceptions import NotFoundException, ConflictException, ForbiddenException
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.redis_service import RedisService
from app.services.email_service import EmailService
from app.core.config import settings
from app.common.enums import UserRole
from app.core.logging import get_logger

logger = get_logger(__name__)

from fastapi import BackgroundTasks


class UserService:
    """Service for user management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(
        self,
        data: UserCreate,
        tenant_id: Optional[UUID] = None,
        role: UserRole = UserRole.USER,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> User:
        """
        Create a new user.

        Args:
            data: User creation data
            tenant_id: Override tenant UUID (for Super Admin)
            role: Initial role for the user
            background_tasks: Background tasks handler

        Returns:
            Created User
        """
        target_tenant_id = tenant_id or data.tenant_id
        if not target_tenant_id and role != UserRole.SUPER_ADMIN:
            raise ForbiddenException("Tenant ID is required")

        # Verify tenant existence if target_tenant_id is provided
        if target_tenant_id:
            tenant_result = await self.db.execute(
                select(Tenant).where(
                    Tenant.id == target_tenant_id,
                    Tenant.is_active == True,
                    Tenant.deleted_at.is_(None),
                )
            )
            if not tenant_result.scalar_one_or_none():
                raise NotFoundException("Tenant deleted or not found")

        # Check for existing username (scoped to tenant)
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.tenant_id == target_tenant_id,
                    User.username == data.username,
                    User.is_active == True,
                    User.deleted_at.is_(None),
                )
            )   
        )
        if result.scalar_one_or_none():
            raise ConflictException(f"Username '{data.username}' already exists ")

        # Check for existing email (scoped to tenant + globally for SuperAdmins)
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.email == data.email,
                    or_(User.tenant_id == target_tenant_id, User.tenant_id.is_(None)),
                )
            )
        )
        if result.scalar_one_or_none():
            raise ConflictException(f"Email '{data.email}' already exists ")

        # Create user
        user = User(
            tenant_id=target_tenant_id,
            first_name=data.first_name,
            last_name=data.last_name,
            username=data.username,
            email=data.email,
            password=hash_password(data.password),
            role=role,
            is_email_verified=False,
            is_active=True,
        )
        self.db.add(user)
        try:
            await self.db.commit()
            await self.db.refresh(user)
        except IntegrityError as e:
            await self.db.rollback()
            error_str = str(e).lower()
            if (
                "foreign key" in error_str
                or "violates foreign key constraint" in error_str
            ):
                raise NotFoundException("Tenant not found")
            if (
                "uq_users_global_email" in error_str
                or "uq_users_tenant_email" in error_str
            ):
                raise ConflictException(f"Email '{data.email}' already exists")
            if (
                "uq_users_global_username" in error_str
                or "uq_users_tenant_username" in error_str
            ):
                raise ConflictException(f"Username '{data.username}' already exists")
            raise ConflictException(
                "Database integrity error: Unique constraint violation"
            )

        # Send verification OTP
        otp = generate_otp()
        expire_seconds = settings.otp_expire_minutes * 60
        await RedisService.store_otp(user.email, otp, expire_seconds, user.tenant_id)

        if background_tasks:
            background_tasks.add_task(EmailService.send_otp_email, user.email, otp)
        else:
            await EmailService.send_otp_email(user.email, otp)

        return user

    async def get_user(self, user_id: UUID, requester: User) -> User:
        """
        Get a user by ID with strict access control.

        Access Rules:
        1. Self-Service: Users can always access their own profile.
        2. SuperAdmin: Can access any TENANT_ADMIN globally.
        3. TenantAdmin: Can access any user within their own tenant.

        Args:
            user_id: Target user UUID
            requester: The user making the request

        Returns:
            User

        Raises:
            NotFoundException: If user not found
            ForbiddenException: If access is denied
        """
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise NotFoundException("User not found")

        # 1. Self-Service
        if requester.id == user.id:
            return user

        # 2. SuperAdmin check: Only TENANT_ADMIN accounts
        if requester.role == UserRole.SUPER_ADMIN:
            if user.role != UserRole.TENANT_ADMIN:
                raise ForbiddenException(
                    "SuperAdmin can only access Tenant Admin accounts"
                )
            return user

        # 3. TenantAdmin check: Same tenant
        if requester.role == UserRole.TENANT_ADMIN:
            if user.tenant_id != requester.tenant_id:
                raise ForbiddenException(
                    "Tenant Admin can only access users in their own tenant"
                )
            return user

        raise ForbiddenException("Access denied")

    async def get_user_by_email(self, email: str, tenant_id: UUID) -> Optional[User]:
        """
        Get a user by email within a tenant.

        Args:
            email: User's email
            tenant_id: Tenant UUID

        Returns:
            User or None
        """
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.tenant_id == tenant_id,
                    User.email == email,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_users_in_tenant(
        self,
        tenant_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[dict], int]:
        """
        Get users based on requester context.

        - If tenant_id is provided: Returns all active users in that tenant.
        - If tenant_id is None: Returns all TENANT_ADMIN users globally (including deleted).
        """
        # Build query
        query = select(User).options(selectinload(User.tenant))
        count_query = select(func.count(User.id))

        filters = []
        if tenant_id:
            # Tenant Admin view: Show all active users in their tenant
            filters.append(User.tenant_id == tenant_id)
            # filters.append(User.deleted_at.is_(None))
        else:
            # Super Admin view: Show all Tenant Admins globally (including deleted)
            filters.append(User.role == UserRole.TENANT_ADMIN)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Get total count
        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        # Get paginated items
        result = await self.db.execute(query.offset(skip).limit(limit))
        users = result.scalars().all()

        return [
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "role": u.role,
                "is_active": u.is_active,
                "is_email_verified": u.is_email_verified,
                "tenant_id": u.tenant_id,
                "tenant_name": u.tenant.name if u.tenant else None,
                "created_at": u.created_at,
                "updated_at": u.updated_at,
                "deleted_at": u.deleted_at,
            }
            for u in users
        ], total

    async def update_user(
        self, user_id: UUID, requester: User, data: UserUpdate
    ) -> User:
        """
        Update a user with access control and restrictions.
        """
        user = await self.get_user(user_id, requester)
        # For uniqueness checks, use the user's actual tenant
        target_tenant_id = user.tenant_id
        update_data = data.model_dump(exclude_unset=True)
        # Restriction: No one can self-change account status (is_active or deleted_at)
        if requester.id == user.id:
            if data.is_active is not None or data.deleted_at is not None:
                raise ForbiddenException(
                    "You cannot modify your own account status (active/deleted)"
                )

        if data.username is not None and data.username != user.username:
            # Check username uniqueness within tenant
            result = await self.db.execute(
                select(User).where(
                    and_(
                        User.tenant_id == target_tenant_id,
                        User.username == data.username,
                    )
                )
            )
            if result.scalar_one_or_none():
                raise ConflictException(f"Username '{data.username}' already exists")
            user.username = data.username

        # # Administrative status updates
        # if "is_active" in data.model_fields_set:
        #     user.is_active = data.is_active

        # if "deleted_at" in data.model_fields_set:
        #     user.deleted_at = data.deleted_at

        # try:
        #     await self.db.commit()
        #     await self.db.refresh(user)
        # except IntegrityError as e:
        #     await self.db.rollback()
        #     error_str = str(e).lower()
        #     if "foreign key" in error_str or "violates foreign key constraint" in error_str:
        #         raise NotFoundException("Tenant not found")
        #     if "uq_users_global_email" in error_str or "uq_users_tenant_email" in error_str:
        #          raise ConflictException("Email already exists")
        #     if "uq_users_global_username" in error_str or "uq_users_tenant_username" in error_str:
        #          raise ConflictException(f"Username '{data.username}' already exists")
        #     raise ConflictException("Database integrity error: Unique constraint violation")
        # return user
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(**update_data)
            .returning(User)  #  PostgreSQL feature
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        updated_user = result.scalar_one()
        return updated_user

    async def deactivate_user(self, user_id: UUID, requester: User) -> Response:
        """
        Deactivate a user (soft delete).
        """
        user = await self.get_user(user_id, requester)
        if not user.is_active or user.deleted_at is not None:
            raise ConflictException("User is already deactivated")
        if requester.id == user.id:
            raise ForbiddenException("You cannot deactivate your own account")

        user.is_active = False
        user.deleted_at = func.now()
        await self.db.commit()
        await self.db.refresh(user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async def resend_verification_otp(
        self,
        user_id: UUID,
        requester: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> bool:
        """
        Resend verification OTP to user.
        """
        user = await self.get_user(user_id, requester)

        otp = generate_otp()
        expire_seconds = settings.otp_expire_minutes * 60
        await RedisService.store_otp(user.email, otp, expire_seconds, user.tenant_id)

        if background_tasks:
            background_tasks.add_task(EmailService.send_otp_email, user.email, otp)
        else:
            await EmailService.send_otp_email(user.email, otp)

        return True
