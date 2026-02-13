"""
Common Schemas

Generic schemas used across multiple modules.
"""

from pydantic import Field, BaseModel, ConfigDict, model_validator
from typing import TypeVar, Generic, List, Any


T = TypeVar("T")


class NormalizedModel(BaseModel):
    """
    Base model that automatically normalizes string inputs.
    
    Features:
    - Strips all whitespace from string fields.
    - Converts all strings to lowercase EXCEPT for sensitive fields.
    """

    @model_validator(mode="before")
    @classmethod
    def normalize_strings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Fields that should NEVER be lowercased (sensitive or Enums)
        bypass_normalization = {
            "password",
            "current_password",
            "new_password",
            "confirm_password",
            "token",
            "refresh_token",
            "otp",
            "role",
            "status",
            "type",
        }

        normalized = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Always strip whitespace
                value = value.strip()

                # Lowercase if not bypassed
                if key not in bypass_normalization:
                    value = value.lower()

            normalized[key] = value

        return normalized


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response schema."""

    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number (1-based)")
    size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")
    data: List[T]

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Generic message response schema."""

    message: str
