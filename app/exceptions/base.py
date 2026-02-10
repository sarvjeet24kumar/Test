"""
Base Exception
"""

from typing import Optional, Any
from fastapi import HTTPException


class MiniMartException(HTTPException):
    """Base exception for MiniMart application."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Any] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        self.code = code
        self.details = details
        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "details": details,
            },
            headers=headers,
        )
