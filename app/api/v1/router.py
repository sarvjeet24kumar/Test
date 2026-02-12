"""
API v1 Router Configuration

Combines all v1 API routers.
"""

from fastapi import APIRouter

from app.api.v1 import auth, users, tenants, shopping_lists, invitations, items, notifications, chat

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])
api_router.include_router(
    invitations.list_router, prefix="/shopping-lists", tags=["Invitations"]
)
api_router.include_router(
    shopping_lists.router, prefix="/shopping-lists", tags=["Shopping Lists"]
)
api_router.include_router(
    items.router, prefix="/shopping-lists", tags=["Items"]
)
api_router.include_router(
    invitations.router, prefix="/invitations", tags=["Invitations"]
)
api_router.include_router(
    chat.router, prefix="/shopping-lists", tags=["Chat"]
)
api_router.include_router(
    notifications.router, prefix="/notifications", tags=["Notifications"]
)
