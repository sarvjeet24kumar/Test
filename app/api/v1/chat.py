"""
Chat Endpoints
"""

from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_verified_user
from app.models.user import User
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.chat_service import ChatService

router = APIRouter()


@router.get(
    "/{list_id}/messages",
    response_model=List[ChatMessageResponse],
    status_code=status.HTTP_200_OK,
)
async def get_chat_messages(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=100),
    after: Optional[str] = Query(None, description="ISO timestamp for cursor pagination"),
):
    """
    Load chat history for a shopping list.
    Only ACCEPTED members can view messages.
    """
    chat_service = ChatService(db)
    return await chat_service.get_messages(
        list_id, current_user, limit=limit, after=after
    )


@router.post(
    "/{list_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_chat_message(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: ChatMessageRequest,
):
    """
    Send a chat message to a shopping list (REST fallback).
    Only ACCEPTED members can send messages.
    """
    chat_service = ChatService(db)
    return await chat_service.send_message(list_id, current_user, data.message)


@router.delete("/{list_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_message(
    list_id: UUID,
    message_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Soft-delete a chat message.
    Only the sender or list owner can delete.
    """
    chat_service = ChatService(db)
    await chat_service.delete_message(list_id, message_id, current_user)
