"""
Base Model

Provides the base class for all SQLAlchemy models with common fields.
"""

from datetime import datetime
from typing import Optional
import uuid

import uuid6
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


class BaseModel(Base):
    """
    Abstract base model with common fields.
    
    Provides:
    - id: UUID primary key (uuid7 for time-ordered IDs)
    - created_at: Creation timestamp
    - updated_at: Last update timestamp
    - deleted_at: Soft delete timestamp (nullable)
    """
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid6.uuid7,
        server_default=func.gen_random_uuid(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
