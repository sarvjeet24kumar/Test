"""
Chat Schemas

Request and response schemas for shopping list chat messages.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.common.constants import MAX_CHAT_MESSAGE_LENGTH


class ChatMessageRequest(BaseModel):
    """Schema for sending a chat message."""

    message: str = Field(
        ..., min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH,
        description="Chat message content",
    )


class ChatMessageResponse(BaseModel):
    """Schema for a single chat message."""

    id: UUID
    shopping_list_id: UUID
    sender_id: UUID
    sender_name: str
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatHistoryResponse(BaseModel):
    """Schema for paginated chat history."""

    messages: List[ChatMessageResponse]
    has_more: bool = False
