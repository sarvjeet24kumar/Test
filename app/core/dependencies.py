"""
FastAPI Dependencies

Dependency injection for authentication, authorization, and database access.
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError
from math import ceil

from app.db.session import get_db
from app.core.security import decode_token
from app.exceptions import (
    UnauthorizedException,
    ForbiddenException,
    TenantInactiveException,
    EmailNotVerifiedException,
    NotFoundException,
    CredentialsException,
)
from app.models.user import User, UserRole
from app.models.tenant import Tenant
from app.models.shopping_list import ShoppingList
from app.models.shopping_list_member import ShoppingListMember, MemberRole
from app.services.redis_service import RedisService


from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Security scheme
security = HTTPBearer(auto_error=True)


class PaginationParams:
    """Dependency for normalized pagination parameters."""
    def __init__(
        self,
        page: int = Query(1),
        size: int = Query(10)
    ):
        self.page = page if page >= 1 else 1
        self.size = size if size >= 1 else 10
        self.skip = (self.page - 1) * self.size


async def get_tenant_id(
    tenant_id: Annotated[Optional[str], Header(alias="Tenant-ID")] = None
) -> Optional[UUID]:
    """
    Dependency to extract Tenant-ID from header.
    
    Returns:
        UUID: If valid UUID provided in header
        None: If header is missing or "None"
    """
    if not tenant_id or tenant_id.lower() == "none":
        return None
        
    try:
        return UUID(tenant_id)
    except ValueError:
        raise NotFoundException("Invalid Tenant-ID format")


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Get the current authenticated user from JWT token.
    
    Validates:
    - Token is present and valid
    - User exists and is active
    - Tenant is active
    
    Returns:
        User: The authenticated user
    
    Raises:
        UnauthorizedException: If token is invalid
        ForbiddenException: If user is inactive
        TenantInactiveException: If tenant is inactive
    """
    try:
        payload = decode_token(credentials.credentials)
    except JWTError as e:
        raise UnauthorizedException(f"Invalid token: {str(e)}")

    # Validate token type
    if payload.get("type") != "access":
        raise UnauthorizedException("Invalid token type")

    # Check if access token is blacklisted (logged out)
    token_id = payload.get("jti")
    if token_id and await RedisService.is_access_token_blacklisted(token_id):
        raise UnauthorizedException("Token has been revoked")

    # Get user
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException("Invalid token payload")

    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException("User not found")

    if not user.is_active:
        raise ForbiddenException("User account is inactive")

    # Check tenant status if associated
    if user.tenant_id:
        result = await db.execute(
            select(Tenant).where(Tenant.id == user.tenant_id)
        )
        tenant = result.scalar_one_or_none()

        if not tenant or not tenant.is_active:
            raise TenantInactiveException()

    return user


async def get_current_verified_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Get current user ensuring email is verified.
    
    Returns:
        User: The authenticated and verified user
    
    Raises:
        EmailNotVerifiedException: If email is not verified
    """
    if not current_user.is_email_verified:
        raise EmailNotVerifiedException()
    return current_user


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory for role-based access control.
    
    Args:
        *allowed_roles: Allowed user roles
    
    Returns:
        Dependency function that validates user role
    """
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_verified_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenException(
                f"This action requires one of these roles: {[r.value for r in allowed_roles]}"
            )
        return current_user

    return role_checker


# Pre-defined role dependencies
RequireSuperAdmin = Depends(require_role(UserRole.SUPER_ADMIN))
RequireTenantAdmin = Depends(require_role(UserRole.TENANT_ADMIN))
RequireUser = Depends(require_role(UserRole.USER, UserRole.TENANT_ADMIN, UserRole.SUPER_ADMIN))


async def get_shopping_list(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShoppingList:
    """
    Get a shopping list ensuring tenant isolation.
    
    Args:
        list_id: Shopping list UUID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        ShoppingList: The requested shopping list
    
    Raises:
        NotFoundException: If list not found
        ForbiddenException: If cross-tenant access attempted
    """
    result = await db.execute(
        select(ShoppingList).where(ShoppingList.id == list_id)
    )
    shopping_list = result.scalar_one_or_none()

    if not shopping_list:
        raise NotFoundException("Shopping list not found")

    # Tenant isolation check
    if shopping_list.tenant_id != current_user.tenant_id:
        raise ForbiddenException("Cross-tenant access denied")

    return shopping_list


async def get_list_membership(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShoppingListMember:
    """
    Get current user's membership in a shopping list.
    
    Args:
        list_id: Shopping list UUID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        ShoppingListMember: The user's membership
    
    Raises:
        NotFoundException: If list not found
        ForbiddenException: If user is not a member or not accepted
    """
    # First verify list exists and tenant matches
    await get_shopping_list(list_id, current_user, db)

    # Check membership
    result = await db.execute(
        select(ShoppingListMember).where(
            ShoppingListMember.shopping_list_id == list_id,
            ShoppingListMember.user_id == current_user.id,
            ShoppingListMember.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise ForbiddenException("You are not an accepted member of this list")

    return membership


async def require_list_owner(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShoppingListMember:
    """
    Require current user to be the owner of a shopping list.
    
    Args:
        list_id: Shopping list UUID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        ShoppingListMember: The owner's membership
    
    Raises:
        ForbiddenException: If user is not the owner
    """
    membership = await get_list_membership(list_id, current_user, db)

    if membership.role != MemberRole.OWNER:
        raise ForbiddenException("Only the list owner can perform this action")

    return membership
