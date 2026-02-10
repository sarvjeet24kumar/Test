"""
Item Endpoints

CRUD operations for shopping list items.
"""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_verified_user
from app.models.user import User
from app.services.list_service import ListService
from app.schemas.item import ItemCreate, ItemUpdate, ItemResponse, ItemStatusUpdate

router = APIRouter()


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: UUID,
    data: ItemUpdate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update an item.
    
    User must be a member of the list containing this item.
    """
    list_service = ListService(db)
    item = await list_service.update_item(item_id, current_user, data)
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


@router.patch("/{item_id}/status", response_model=ItemResponse)
async def update_item_status(
    item_id: UUID,
    data: ItemStatusUpdate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Quick update for item status (mark as purchased/pending).
    
    User must be a member of the list containing this item.
    """
    list_service = ListService(db)
    item = await list_service.update_item(
        item_id, current_user, ItemUpdate(status=data.status)
    )
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


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete an item.
    
    User must be a member of the list containing this item.
    """
    list_service = ListService(db)
    await list_service.delete_item(item_id, current_user)
