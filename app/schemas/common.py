"""
Common Schemas

Generic schemas used across multiple modules.
"""

from typing import TypeVar, Generic, List
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response schema."""

    items: List[T]
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number (1-based)")
    size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")
