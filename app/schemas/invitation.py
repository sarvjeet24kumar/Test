"""
Invitation Schemas

Request and response schemas for stateless invitation handling.
"""

from uuid import UUID
from pydantic import BaseModel

from app.models.shopping_list_member import MemberRole


class InvitationAcceptRequest(BaseModel):
    """Accept invitation request."""

    token: str


class InvitationRejectRequest(BaseModel):
    """Reject invitation request."""

    token: str


class InvitationAcceptResponse(BaseModel):
    """Accept invitation response."""

    message: str = "Invitation accepted"
    list: "AcceptedListInfo"


class AcceptedListInfo(BaseModel):
    """Accepted list information."""

    id: UUID
    name: str
    role: MemberRole = MemberRole.MEMBER


# Rebuild for forward reference
InvitationAcceptResponse.model_rebuild()


class InvitationRejectResponse(BaseModel):
    """Reject invitation response."""

    message: str = "Invitation rejected"


class InvitationTokenPayload(BaseModel):
    """Invitation token payload structure (internal use)."""

    type: str = "list_invite"
    list_id: UUID
    email: str
    tenant_id: UUID
    inviter_id: UUID
    jti: str  # unique token identifier
