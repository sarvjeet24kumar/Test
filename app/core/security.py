"""
Security Utilities

Password hashing, JWT token operations, and OTP generation.
"""

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict
from uuid import UUID, uuid4

from jose import jwt, JWTError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings


# Password hashing
ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False


def create_access_token(
    user_id: UUID,
    tenant_id: Optional[UUID],
    role: str,
    email: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: User's UUID
        tenant_id: User's tenant UUID
        role: User's role
        email: User's email
        expires_delta: Optional custom expiration time
    
    Returns:
        Encoded JWT string
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid4()),
        "type": "access",
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: UUID,
    tenant_id: Optional[UUID],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT refresh token.
    
    Args:
        user_id: User's UUID
        tenant_id: User's tenant UUID
        expires_delta: Optional custom expiration time
    
    Returns:
        Encoded JWT string
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid4()),
        "type": "refresh",
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT string to decode
    
    Returns:
        Token payload dictionary
    
    Raises:
        JWTError: If token is invalid or expired
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    return payload


def generate_otp(length: Optional[int] = None) -> str:
    """
    Generate a random OTP code.
    
    Args:
        length: OTP length (default from settings)
    
    Returns:
        Numeric OTP string
    """
    if length is None:
        length = settings.otp_length
    return "".join(secrets.choice(string.digits) for _ in range(length))


def create_invitation_token(
    list_id: UUID,
    email: str,
    tenant_id: Optional[UUID],
    inviter_id: UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT invitation token for list invites.
    
    Args:
        list_id: Shopping list UUID
        email: Invitee's email
        tenant_id: Tenant UUID
        inviter_id: Inviter's user UUID
        expires_delta: Optional custom expiration time
    
    Returns:
        Encoded JWT invitation token
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            hours=settings.invitation_token_expire_hours
        )

    payload = {
        "type": "list_invite",
        "list_id": str(list_id),
        "email": email,
        "tenant_id": str(tenant_id),
        "inviter_id": str(inviter_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid4()),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_invitation_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate an invitation token.
    
    Args:
        token: JWT invitation token
    
    Returns:
        Token payload dictionary
    
    Raises:
        JWTError: If token is invalid or expired
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    
    # Validate token type
    if payload.get("type") != "list_invite":
        raise JWTError("Invalid token type")
    
    return payload
