"""
Validation exceptions
"""

from typing import Optional, Any
from fastapi import status
from app.exceptions.base import MiniMartException


class ValidationException(MiniMartException):
    """422 Unprocessable Entity - Validation error."""

    def __init__(
        self,
        message: str = "Validation error",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message=message,
            details=details,
        )
