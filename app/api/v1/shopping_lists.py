"""
Shopping List Endpoints

CRUD operations for shopping lists and membership management.
"""

from typing import Annotated, List
from uuid import UUID
from fastapi import BackgroundTasks
from fastapi import APIRouter, Depends, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_verified_user, PaginationParams
from app.models.user import User
from app.services.list_service import ListService
from app.services.invitation_service import InvitationService
from app.schemas.shopping_list import (
    ShoppingListCreate,
    ShoppingListUpdate,
    ShoppingListResponse,
    ShoppingListDetailResponse,
    ShoppingListSummaryResponse,
)
from app.schemas.shopping_list_member import (
    MemberResponse,
    InviteRequest,
    InviteResponse,
    RemoveMemberResponse,
    LeaveListResponse,
)
from math import ceil
from app.schemas.common import PaginatedResponse
from app.models.item import ItemStatus

router = APIRouter()


# ==================== Shopping List CRUD ====================


@router.post(
    "",
    response_model=ShoppingListResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shopping_list(
    data: ShoppingListCreate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new shopping list.
    
    The creating user becomes the Owner with full permissions.
    """
    list_service = ListService(db)
    return await list_service.create_list(current_user, data)


@router.get("", response_model=PaginatedResponse[ShoppingListSummaryResponse])
async def list_shopping_lists(
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
):
    """
    Get all shopping lists the user is a member of.
    
    Returns a summary with item and member counts.
    """
    list_service = ListService(db)
    items, total = await list_service.get_user_lists(
        current_user, skip=pagination.skip, limit=pagination.size
    )
    
    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=ceil(total / pagination.size) if total > 0 else 1,
    )


@router.get("/{list_id}", response_model=ShoppingListDetailResponse)
async def get_shopping_list(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get a shopping list with members and items.
    
    User must be a member of the list.
    """
    list_service = ListService(db)
    shopping_list = await list_service.get_list(list_id, current_user)
    
    # Build detailed response
    members = [
        {
            "user_id": m.user_id,
            "username": m.user.username if m.user else "Unknown",
            "role": m.role.value,
            "joined_at": m.joined_at,
        }
        for m in shopping_list.members
    ]
    
    items = [
        {
            "id": item.id,
            "name": item.name,
            "quantity": item.quantity,
            "status": item.status.value,
            "added_by": item.added_by,
            "created_at": item.created_at,
        }
        for item in shopping_list.items
    ]
    
    pending_count = sum(1 for i in shopping_list.items if i.status == ItemStatus.PENDING)
    purchased_count = sum(1 for i in shopping_list.items if i.status == ItemStatus.PURCHASED)
    
    return ShoppingListDetailResponse(
        id=shopping_list.id,
        name=shopping_list.name,
        tenant_id=shopping_list.tenant_id,
        owner_id=shopping_list.owner_id,
        created_at=shopping_list.created_at,
        updated_at=shopping_list.updated_at,
        members=members,
        items=items,
        item_count=len(shopping_list.items),
        pending_count=pending_count,
        purchased_count=purchased_count,
    )


@router.patch("/{list_id}", response_model=ShoppingListResponse)
async def update_shopping_list(
    list_id: UUID,
    data: ShoppingListUpdate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a shopping list.
    
    **Owner only.**
    """
    list_service = ListService(db)
    return await list_service.update_list(list_id, current_user, data)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shopping_list(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a shopping list.
    
    **Owner only.** All items and memberships will be deleted.
    """
    list_service = ListService(db)
    await list_service.delete_list(list_id, current_user)


@router.get("/{list_id}/members", response_model=PaginatedResponse[MemberResponse])
async def list_members(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
):
    """
    Get all members of a shopping list.
    
    User must be a member of the list.
    """
    list_service = ListService(db)
    members, total = await list_service.get_members(
        list_id, current_user, skip=pagination.skip, limit=pagination.size
    )
    
    items = [
        MemberResponse(
            id=m.id,
            user_id=m.user_id,
            username=m.user.username if m.user else "Unknown",
            email=m.user.email if m.user else "",
            role=m.role,
            joined_at=m.joined_at,
        )
        for m in members
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=ceil(total / pagination.size) if total > 0 else 1,
    )


@router.post("/{list_id}/invite", response_model=InviteResponse)
async def invite_member(
    list_id: UUID,
    data: InviteRequest,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """
    Invite a user to join the shopping list.
    
    **Owner only.**
    
    An invitation email will be sent with accept/reject links.
    """
    invitation_service = InvitationService(db)
    expires_at = await invitation_service.send_invitation(
        list_id, data.email, current_user, background_tasks
    )
    return InviteResponse(expires_at=expires_at)


@router.delete(
    "/{list_id}/members/{user_id}",
    response_model=RemoveMemberResponse,
)
async def remove_member(
    list_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Remove a member from the shopping list.
    
    **Owner only.** Cannot remove the owner.
    """
    list_service = ListService(db)
    await list_service.remove_member(list_id, user_id, current_user)
    return RemoveMemberResponse()


@router.delete("/{list_id}/members/me", response_model=LeaveListResponse)
async def leave_list(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Leave a shopping list.
    
    **Members only.** Owner cannot leave their own list.
    """
    list_service = ListService(db)
    await list_service.leave_list(list_id, current_user)
    return LeaveListResponse()


# ==================== Item Operations ====================


from app.schemas.item import ItemCreate, ItemResponse


@router.post(
    "/{list_id}/items",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_item(
    list_id: UUID,
    data: ItemCreate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Add an item to a shopping list.
    
    User must be a member of the list.
    """
    list_service = ListService(db)
    item = await list_service.add_item(list_id, current_user, data)
    return ItemResponse(
        id=item.id,
        shopping_list_id=item.shopping_list_id,
        added_by=item.added_by,
        name=item.name,
        quantity=item.quantity,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/{list_id}/items", response_model=PaginatedResponse[ItemResponse])
async def get_items(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
):
    """
    Get all items in a shopping list.
    
    User must be a member of the list.
    """
    list_service = ListService(db)
    items, total = await list_service.get_items(
        list_id, current_user, skip=pagination.skip, limit=pagination.size
    )
    
    results = [
        ItemResponse(
            id=item.id,
            shopping_list_id=item.shopping_list_id,
            added_by=item.added_by,
            name=item.name,
            quantity=item.quantity,
            status=item.status,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]

    return PaginatedResponse(
        items=results,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=ceil(total / pagination.size) if total > 0 else 1,
    )

