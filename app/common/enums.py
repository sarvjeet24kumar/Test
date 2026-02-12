"""
Centralized Enums

All application enums in one place — imported by models, services, and APIs.
"""

import enum


class UserRole(str, enum.Enum):
    """User roles for platform-level access control."""

    SUPER_ADMIN = "SUPER_ADMIN"
    TENANT_ADMIN = "TENANT_ADMIN"
    USER = "USER"


class MemberRole(str, enum.Enum):
    """Roles for shopping list membership."""

    OWNER = "OWNER"
    MEMBER = "MEMBER"


class ItemStatus(str, enum.Enum):
    """Status of a shopping list item."""

    PENDING = "PENDING"
    PURCHASED = "PURCHASED"


class InviteStatus(str, enum.Enum):
    """Status of an invitation."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class NotificationType(str, enum.Enum):
    """Types of notifications."""

    LIST_INVITE = "LIST_INVITE"
    INVITE_ACCEPTED = "INVITE_ACCEPTED"
    INVITE_REJECTED = "INVITE_REJECTED"
    ITEM_ADDED = "ITEM_ADDED"
    ITEM_UPDATED = "ITEM_UPDATED"
    ITEM_DELETED = "ITEM_DELETED"
    ITEM_PURCHASED = "ITEM_PURCHASED"
    CHAT_MESSAGE = "CHAT_MESSAGE"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    LIST_UPDATED = "LIST_UPDATED"
