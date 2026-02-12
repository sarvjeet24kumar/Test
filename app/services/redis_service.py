"""
Redis Service

Manages Redis connections and operations for tokens, OTP, and pub/sub.
"""

from typing import Optional
import redis.asyncio as redis
from uuid import UUID
from app.core.config import settings


class RedisService:
    """Service for Redis operations."""

    _client: Optional[redis.Redis] = None
    _token_client: Optional[redis.Redis] = None

    @classmethod
    async def get_client(cls) -> redis.Redis:
        """Get the main Redis client."""
        if cls._client is None:
            cls._client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return cls._client

    @classmethod
    async def get_token_client(cls) -> redis.Redis:
        """Get the Redis client for token storage."""
        if cls._token_client is None:
            # Parse the URL and change the database
            base_url = settings.redis_url.rsplit("/", 1)[0]
            token_url = f"{base_url}/{settings.redis_token_db}"
            cls._token_client = redis.from_url(
                token_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return cls._token_client

    @classmethod
    async def close(cls) -> None:
        """Close all Redis connections."""
        if cls._client:
            await cls._client.close()
            cls._client = None
        if cls._token_client:
            await cls._token_client.close()
            cls._token_client = None

    # OTP Operations
    @classmethod
    async def store_otp(cls, email: str, otp: str, expire_seconds: int,tenant_id:"UUID") -> None:
        """Store OTP for email verification."""
        client = await cls.get_token_client()
        key = f"otp:{tenant_id}:{email}"
        await client.setex(key, expire_seconds, otp)

    @classmethod
    async def get_otp(cls, email: str,tenant_id:"UUID") -> Optional[str]:
        """Get stored OTP for email."""
        client = await cls.get_token_client()
        key = f"otp:{tenant_id}:{email}"
        return await client.get(key)

    @classmethod
    async def delete_otp(cls, email: str,tenant_id:"UUID") -> None:
        """Delete OTP after successful verification."""
        client = await cls.get_token_client()
        key = f"otp:{tenant_id}:{email}"
        await client.delete(key)

    # Invitation Token Operations
    @classmethod
    async def store_invitation_token(
        cls, token_id: str, list_id: str, expire_seconds: int
    ) -> None:
        """Store invitation token for validation."""
        client = await cls.get_token_client()
        key = f"invite:{token_id}"
        await client.setex(key, expire_seconds, list_id)

    @classmethod
    async def validate_invitation_token(cls, token_id: str) -> Optional[str]:
        """Check if invitation token exists and return list_id."""
        client = await cls.get_token_client()
        key = f"invite:{token_id}"
        return await client.get(key)

    @classmethod
    async def invalidate_invitation_token(cls, token_id: str) -> None:
        """Delete invitation token after use."""
        client = await cls.get_token_client()
        key = f"invite:{token_id}"
        await client.delete(key)

    # Refresh Token Blacklist
    @classmethod
    async def blacklist_token(cls, token_id: str, expire_seconds: int) -> None:
        """Add token to blacklist."""
        client = await cls.get_token_client()
        key = f"blacklist:{token_id}"
        await client.setex(key, expire_seconds, "1")

    @classmethod
    async def is_token_blacklisted(cls, token_id: str) -> bool:
        """Check if token is blacklisted."""
        client = await cls.get_token_client()
        key = f"blacklist:{token_id}"
        return await client.exists(key) > 0

    # Access Token Blacklist (for logout)
    @classmethod
    async def blacklist_access_token(cls, token_id: str, expire_seconds: int) -> None:
        """Add access token to blacklist in Redis."""
        client = await cls.get_token_client()
        key = f"blacklist:access:{token_id}"
        await client.setex(key, expire_seconds, "1")

    @classmethod
    async def is_access_token_blacklisted(cls, token_id: str) -> bool:
        """Check if access token is blacklisted in Redis."""
        client = await cls.get_token_client()
        key = f"blacklist:access:{token_id}"
        return await client.exists(key) > 0


    # Password Reset Token Operations
    @classmethod
    async def store_password_reset_jti(
        cls, jti: str, user_id: str, expire_seconds: int = 900
    ) -> None:
        """Store password reset JTI for single-use validation (default 15 min)."""
        client = await cls.get_token_client()
        key = f"password_reset:{jti}"
        await client.setex(key, expire_seconds, user_id)

    @classmethod
    async def validate_password_reset_jti(cls, jti: str) -> Optional[str]:
        """Check if password reset JTI exists. Returns user_id or None."""
        client = await cls.get_token_client()
        key = f"password_reset:{jti}"
        return await client.get(key)

    @classmethod
    async def delete_password_reset_jti(cls, jti: str) -> None:
        """Delete password reset JTI after use."""
        client = await cls.get_token_client()
        key = f"password_reset:{jti}"
        await client.delete(key)

