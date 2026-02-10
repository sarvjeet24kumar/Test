"""
Authentication Schemas

Request and response schemas for authentication endpoints.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Login request payload."""

    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class LoginResponse(BaseModel):
    """Login response with tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(..., description="Access token expiry in seconds")


class TokenPayload(BaseModel):
    """JWT token payload structure."""

    sub: UUID  # user_id
    tenant_id: UUID
    role: str
    email: str
    exp: datetime
    iat: datetime
    jti: str  # unique token identifier
    type: str = "access"  # access or refresh


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


class VerifyEmailRequest(BaseModel):
    """Email verification request with OTP."""

    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)

class ResendOtpRequest(BaseModel):
    email: EmailStr

class OTPResponse(BaseModel):
    """OTP sent response."""

    message: str = "OTP sent successfully"
    expires_in: int = Field(..., description="OTP expiry in seconds")


class PasswordResetRequest(BaseModel):
    """Password reset request."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation."""

    token: str
    new_password: str = Field(..., min_length=8, max_length=128)
