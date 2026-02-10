"""
Invitation Endpoints

Handle invitation acceptance and rejection.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_verified_user
from app.models.user import User
from app.services.invitation_service import InvitationService
from app.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationRejectRequest,
    InvitationAcceptResponse,
    InvitationRejectResponse,
    AcceptedListInfo,
)
from app.models.shopping_list_member import MemberRole

router = APIRouter()


@router.post("/accept", response_model=InvitationAcceptResponse)
async def accept_invitation(
    data: InvitationAcceptRequest,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Accept a shopping list invitation.
    
    **Requires authentication.** The invitation email must match the
    logged-in user's email.
    """
    invitation_service = InvitationService(db)
    shopping_list = await invitation_service.accept_invitation(
        data.token, current_user
    )
    
    return InvitationAcceptResponse(
        list=AcceptedListInfo(
            id=shopping_list.id,
            name=shopping_list.name,
            role=MemberRole.MEMBER,
        )
    )


@router.post("/reject", response_model=InvitationRejectResponse)
async def reject_invitation(
    data: InvitationRejectRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Reject a shopping list invitation.
    
    Does not require authentication. No database changes occur.
    """
    invitation_service = InvitationService(db)
    await invitation_service.reject_invitation(data.token)
    return InvitationRejectResponse()
