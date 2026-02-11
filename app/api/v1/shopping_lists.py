"""
Shopping List Endpoints

CRUD operations for shopping lists, membership management, invitations, and chat.
Permission matrix enforced via ListService.

NOTE: Item endpoints have been moved to app/api/v1/items.py
"""

from typing import Annotated, Optional, List
from uuid import UUID
from math import ceil

from fastapi import APIRouter, Depends, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_verified_user, PaginationParams
from app.core.responses import success_response
from app.models.user import User
from app.services.list_service import ListService
from app.schemas.shopping_list import (
    ShoppingListCreate,
    ShoppingListUpdate,
    ShoppingListResponse,
    ShoppingListDetailResponse,
    ShoppingListSummaryResponse,
)
from app.schemas.shopping_list_member import (
    MemberResponse,
    RemoveMemberResponse,
    LeaveListResponse,
    UpdateMemberPermissions,
)
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.schemas.common import ResponseEnvelope, PaginatedResponse, MessageResponse
from app.common.enums import ItemStatus
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ==================== Shopping List CRUD ====================


@router.post(
    "",
    response_model=ResponseEnvelope[ShoppingListResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_shopping_list(
    data: ShoppingListCreate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new shopping list.
    
    Allowed: Tenant Admin, User.
    Blocked: Super Admin.
    """
    list_service = ListService(db)
    sl = await list_service.create_list(current_user, data)
    return success_response(sl)


@router.get(
    "",
    response_model=ResponseEnvelope[PaginatedResponse[ShoppingListSummaryResponse]],
    status_code=status.HTTP_200_OK,
)
async def list_shopping_lists(
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
):
    """
    Get all shopping lists visible to the user.
    """
    list_service = ListService(db)
    items, total = await list_service.get_user_lists(
        current_user, skip=pagination.skip, limit=pagination.size
    )
    
    return success_response({
        "items": items,
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if total > 0 else 1,
    })




@router.get(
    "/{list_id}",
    response_model=ResponseEnvelope[ShoppingListDetailResponse],
    status_code=status.HTTP_200_OK,
)
async def get_shopping_list(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get a shopping list with members and items.
    """
    list_service = ListService(db)
    shopping_list = await list_service.get_list(list_id, current_user)
    
    shopping_list.item_count = len(shopping_list.items)
    shopping_list.pending_count = sum(1 for i in shopping_list.items if i.status == ItemStatus.PENDING)
    shopping_list.purchased_count = sum(1 for i in shopping_list.items if i.status == ItemStatus.PURCHASED)
    
    return success_response(shopping_list)


@router.patch(
    "/{list_id}",
    response_model=ResponseEnvelope[ShoppingListResponse],
    status_code=status.HTTP_200_OK,
)
async def update_shopping_list(
    list_id: UUID,
    data: ShoppingListUpdate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a shopping list.
    Allowed: Tenant Admin, Owner.
    """
    list_service = ListService(db)
    sl = await list_service.update_list(list_id, current_user, data)
    return success_response(sl)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shopping_list(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a shopping list.
    """
    list_service = ListService(db)
    await list_service.delete_list(list_id, current_user)


# ==================== Member Operations ====================


@router.get(
    "/{list_id}/members",
    response_model=ResponseEnvelope[PaginatedResponse[MemberResponse]],
    status_code=status.HTTP_200_OK,
)
async def list_members(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
):
    """
    Get all members of a shopping list.
    """
    list_service = ListService(db)
    members, total = await list_service.get_members(
        list_id, current_user, skip=pagination.skip, limit=pagination.size
    )
    
    return success_response({
        "items": members,
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if total > 0 else 1,
    })




@router.delete(
    "/{list_id}/members/{user_id}",
    response_model=ResponseEnvelope[MessageResponse],
    status_code=status.HTTP_200_OK,
)
async def remove_member(
    list_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Remove a member from the shopping list.
    """
    list_service = ListService(db)
    await list_service.remove_member(list_id, user_id, current_user)
    return success_response({"message": "Member removed successfully"})


@router.patch(
    "/{list_id}/members/{user_id}/permissions",
    response_model=ResponseEnvelope[MemberResponse],
    status_code=status.HTTP_200_OK,
)
async def update_member_permissions(
    list_id: UUID,
    user_id: UUID,
    data: UpdateMemberPermissions,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a member's permission flags.
    """
    list_service = ListService(db)
    member = await list_service.update_member_permissions(
        list_id, user_id, current_user, data
    )
    return success_response(member)


@router.delete(
    "/{list_id}/members/me",
    response_model=ResponseEnvelope[MessageResponse],
    status_code=status.HTTP_200_OK,
)
async def leave_list(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Leave a shopping list.
    Members only. Owner cannot leave their own list.
    """
    list_service = ListService(db)
    await list_service.leave_list(list_id, current_user)
    return success_response({"message": "Left list successfully"})




# ==================== Chat (REST) ====================


@router.get(
    "/{list_id}/messages",
    response_model=ResponseEnvelope[List[ChatMessageResponse]],
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
    from app.services.chat_service import ChatService
    chat_service = ChatService(db)
    messages = await chat_service.get_messages(
        list_id, current_user, limit=limit, after=after
    )
    return success_response(messages)


@router.post(
    "/{list_id}/messages",
    response_model=ResponseEnvelope[ChatMessageResponse],
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
    from app.services.chat_service import ChatService
    chat_service = ChatService(db)
    message = await chat_service.send_message(list_id, current_user, data.message)
    return success_response(message)


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
    from app.services.chat_service import ChatService
    chat_service = ChatService(db)
    await chat_service.delete_message(list_id, message_id, current_user)
