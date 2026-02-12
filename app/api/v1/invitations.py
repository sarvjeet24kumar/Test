"""
Invitation Endpoints

Handle invitation acceptance, rejection, cancellation, and resending.
"""

from typing import Annotated, Optional
from uuid import UUID
from math import ceil

from fastapi import APIRouter, Depends, BackgroundTasks, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_verified_user, PaginationParams
from app.models.user import User
from app.services.invitation_service import InvitationService
from app.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationRejectRequest,
    InvitationResponse,
    InviteRequest,
    InviteResponse,
)
from app.schemas.common import PaginatedResponse, MessageResponse
from app.common.enums import MemberRole

router = APIRouter()
list_router = APIRouter()


@router.post(
    "/accept",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def accept_invitation(
    data: InvitationAcceptRequest,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Accept a shopping list invitation.
    Requires authentication. Invitation email must match logged-in user's email.
    """
    invitation_service = InvitationService(db)
    await invitation_service.accept_invitation(
        data.token, current_user
    )
    return MessageResponse(message="Invitation accepted")


@router.post(
    "/reject",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def reject_invitation(
    data: InvitationRejectRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Reject a shopping list invitation.
    Does not require authentication.
    """
    invitation_service = InvitationService(db)
    await invitation_service.reject_invitation(data.token)
    return MessageResponse(message="Invitation rejected")


@router.delete(
    "/{invite_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_invitation(
    invite_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Cancel a pending invitation.
    Only the list owner or tenant admin can cancel.
    """
    invitation_service = InvitationService(db)
    await invitation_service.cancel_invitation(invite_id, current_user)
    return MessageResponse(message="Invitation cancelled")


@router.post(
    "/{invite_id}/resend",
    response_model=InviteResponse,
    status_code=status.HTTP_200_OK,
)
async def resend_invitation(
    invite_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """
    Resend a pending invitation — rotates token and resets expiry.
    Only the list owner or tenant admin can resend.
    """
    invitation_service = InvitationService(db)
    expires_at = await invitation_service.resend_invitation(
        invite_id, current_user, background_tasks
    )
    return InviteResponse(
        message="Invitation resent successfully",
        expires_at=expires_at,
    )


# ==================== List-Scoped Invitation Endpoints ====================
# These are mounted under /shopping-lists


@list_router.get(
    "/invites",
    response_model=PaginatedResponse[InvitationResponse],
    status_code=status.HTTP_200_OK,
)
async def get_my_invites(
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
    status_filter: Optional[str] = Query(
        None, alias="status",
        description="Filter by status: PENDING, ACCEPTED, REJECTED, CANCELLED, EXPIRED"
    ),
):
    """
    Get all invitations for the current user across all lists.
    Supports filtering by status.
    """
    invitation_service = InvitationService(db)
    invites, total = await invitation_service.get_my_invites(
        current_user,
        status_filter=status_filter,
        skip=pagination.skip,
        limit=pagination.size,
    )
    return PaginatedResponse(
        data=invites,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=ceil(total / pagination.size) if total > 0 else 1,
    )


@list_router.post(
    "/{list_id}/invite",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    list_id: UUID,
    data: InviteRequest,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """
    Invite a user to join the shopping list.
    Allowed: Tenant Admin, Owner.
    """
    invitation_service = InvitationService(db)
    expires_at = await invitation_service.send_invitation(
        list_id, data.user_id, current_user, background_tasks
    )
    return InviteResponse(
        message="Invitation sent successfully",
        expires_at=expires_at,
    )


@list_router.get(
    "/{list_id}/invites",
    response_model=PaginatedResponse[InvitationResponse],
    status_code=status.HTTP_200_OK,
)
async def get_list_invites(
    list_id: UUID,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Annotated[PaginationParams, Depends()],
    status_filter: Optional[str] = Query(
        None, alias="status",
        description="Filter by status: PENDING, ACCEPTED, REJECTED, CANCELLED, EXPIRED"
    ),
):
    """
    Get all invitations for a specific shopping list.
    Allowed: Owner, Tenant Admin.
    """
    invitation_service = InvitationService(db)
    invites, total = await invitation_service.get_list_invites(
        list_id,
        current_user,
        status_filter=status_filter,
        skip=pagination.skip,
        limit=pagination.size,
    )
    return PaginatedResponse(
        data=invites,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=ceil(total / pagination.size) if total > 0 else 1,
    )
