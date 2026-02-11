"""
Password Validation Utility

Enforces password strength requirements.
"""

import re

from app.exceptions.base import MiniMartException


def validate_password_strength(password: str) -> None:
    """
    Validate password meets security requirements.

    Rules:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit

    Raises:
        MiniMartException: with code WEAK_PASSWORD if validation fails
    """
    if (
        len(password) >= 8
        and re.search(r"[A-Z]", password)
        and re.search(r"[a-z]", password)
        and re.search(r"[0-9]", password)
    ):
        return

    raise MiniMartException(
        status_code=400,
        code="WEAK_PASSWORD",
        message="Password does not meet security requirements.",
        details={
            "password": [
                "Must contain at least 8 characters, one uppercase, one lowercase, and one number."
            ]
        },
    )
