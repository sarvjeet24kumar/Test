"""
API v1 Router Configuration

Combines all v1 API routers.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.users import router as users_router
from app.api.v1.shopping_lists import router as lists_router
from app.api.v1.items import router as items_router
from app.api.v1.invitations import router as invitations_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(tenants_router, prefix="/tenants", tags=["Tenants"])
router.include_router(users_router, prefix="/users", tags=["Users"])
router.include_router(lists_router, prefix="/shopping-lists", tags=["Shopping Lists"])
router.include_router(items_router, prefix="/items", tags=["Items"])
router.include_router(invitations_router, prefix="/invitations", tags=["Invitations"])
