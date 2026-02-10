"""
Auth exceptions
"""

from typing import Optional, Any, Dict
from fastapi import status
from app.exceptions.base import MiniMartException


class CredentialsException(MiniMartException):
    """401 Unauthorized - Could not validate credentials."""

    def __init__(
        self,
        message: str = "Could not validate credentials",
        headers: Optional[Dict[str, str]] = None,
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="CREDENTIALS_ERROR",
            message=message,
            headers=headers,
            details=details,
        )


class UnauthorizedException(MiniMartException):
    """401 Unauthorized - Missing or invalid credentials."""

    def __init__(
        self,
        message: str = "Invalid credentials",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message=message,
            details=details,
        )


class ForbiddenException(MiniMartException):
    """403 Forbidden - Insufficient permissions."""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message=message,
            details=details,
        )


class EmailNotVerifiedException(MiniMartException):
    """403 Forbidden - Email not verified."""

    def __init__(
        self,
        message: str = "Email not verified",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="EMAIL_NOT_VERIFIED",
            message=message,
            details=details,
        )


class InvitationExpiredException(MiniMartException):
    """400 Bad Request - Invitation has expired."""

    def __init__(
        self,
        message: str = "Invitation has expired",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVITATION_EXPIRED",
            message=message,
            details=details,
        )


class InvitationAlreadyUsedException(MiniMartException):
    """400 Bad Request - Invitation has already been used."""

    def __init__(
        self,
        message: str = "Invitation has already been used",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVITATION_USED",
            message=message,
            details=details,
        )
