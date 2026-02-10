"""Schemas Package"""

from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    TokenPayload,
    RefreshTokenRequest,
    VerifyEmailRequest,
    OTPResponse,
)
from app.schemas.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
)
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserWithTenantResponse,
)
from app.schemas.shopping_list import (
    ShoppingListCreate,
    ShoppingListUpdate,
    ShoppingListResponse,
    ShoppingListDetailResponse,
)
from app.schemas.shopping_list_member import (
    MemberResponse,
    InviteRequest,
    InviteResponse,
)
from app.schemas.item import (
    ItemCreate,
    ItemUpdate,
    ItemResponse,
)
from app.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationRejectRequest,
    InvitationAcceptResponse,
)

__all__ = [
    # Auth
    "LoginRequest",
    "LoginResponse",
    "TokenPayload",
    "RefreshTokenRequest",
    "VerifyEmailRequest",
    "OTPResponse",
    # Tenant
    "TenantCreate",
    "TenantUpdate",
    "TenantResponse",
    # User
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserWithTenantResponse",
    # Shopping List
    "ShoppingListCreate",
    "ShoppingListUpdate",
    "ShoppingListResponse",
    "ShoppingListDetailResponse",
    # Member
    "MemberResponse",
    "InviteRequest",
    "InviteResponse",
    # Item
    "ItemCreate",
    "ItemUpdate",
    "ItemResponse",
    # Invitation
    "InvitationAcceptRequest",
    "InvitationRejectRequest",
    "InvitationAcceptResponse",
]
