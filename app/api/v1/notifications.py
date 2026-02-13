"""
Notification Endpoints
"""

from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_verified_user, PaginationParams
from app.models.user import User
from app.services.notification_service import NotificationService
from app.schemas.notification import NotificationResponse, NotificationUpdate
from app.schemas.common import PaginatedResponse, MessageResponse
from app.models.notification import Notification
from app.exceptions import NotFoundException
from sqlalchemy import select, func
from math import ceil

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedResponse[NotificationResponse],
    status_code=status.HTTP_200_OK,
)
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
    is_read: Optional[bool] = Query(None, description="Filter by read/unread status"),
):
    """
    Get notifications for the current user.
    """
    notification_service = NotificationService(db)
    items = await notification_service.get_user_notifications(
        current_user.id,
        is_read=is_read,
        limit=pagination.size,
        skip=pagination.skip,
    )
    
    # We don't have a specific total count helper in service that returns items + total yet
    # but for notifications we just need the list. Let's do a quick count.
    count_query = select(func.count(Notification.id)).where(Notification.user_id == current_user.id)
    if is_read is not None:
        count_query = count_query.where(Notification.is_read == is_read)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    return PaginatedResponse(
        data=items,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=ceil(total / pagination.size) if total > 0 else 1,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_notification_read(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Mark a notification as read.
    """
    notification_service = NotificationService(db)
    success = await notification_service.mark_as_read(notification_id, current_user.id)
    if not success:
        raise NotFoundException("Notification not found or already read")
    
    return MessageResponse(message="Notification marked as read")


@router.post(
    "/read-all",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_all_notifications_read(
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Mark all unread notifications as read.
    """
    notification_service = NotificationService(db)
    count = await notification_service.mark_all_as_read(current_user.id)
    return MessageResponse(message=f"Marked {count} notifications as read")
