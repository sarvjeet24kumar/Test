"""
User and Tenant exceptions
"""

from typing import Optional, Any
from fastapi import status
from app.exceptions.base import MiniMartException


class NotFoundException(MiniMartException):
    """404 Not Found - Resource not found."""

    def __init__(
        self,
        message: str = "Resource not found",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message=message,
            details=details,
        )


class ConflictException(MiniMartException):
    """409 Conflict - Resource already exists."""

    def __init__(
        self,
        message: str = "Resource already exists",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="CONFLICT",
            message=message,
            details=details,
        )


class TenantInactiveException(MiniMartException):
    """403 Forbidden - Tenant is inactive."""

    def __init__(
        self,
        message: str = "Tenant is inactive",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="TENANT_INACTIVE",
            message=message,
            details=details,
        )


class RateLimitException(MiniMartException):
    """429 Too Many Requests - Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMITED",
            message=message,
            details=details,
        )
