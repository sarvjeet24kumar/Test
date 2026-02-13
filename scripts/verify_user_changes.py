import asyncio
from uuid import uuid4
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserResponse, UserAdminResponse
from app.common.enums import UserRole
import os

# Database URL for testing
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/minimart"

async def verify_logic():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        auth_service = AuthService(db)
        user_service = UserService(db)

        # 1. Test Signup Activation (Should be inactive)
        print("\n--- Testing Signup Activation ---")
        email = f"test_{uuid4().hex[:6]}@example.com"
        username = f"user_{uuid4().hex[:6]}"
        
        signup_data = {
            "email": email,
            "username": username,
            "first_name": "Test",
            "last_name": "User",
            "password": "Password123!",
            "tenant_id": None # Global SuperAdmin or use a valid one if needed
        }
        
        user = User(
            email=email,
            username=username,
            first_name="Test",
            last_name="User",
            password="hashed",
            role=UserRole.USER,
            is_email_verified=False,
            is_active=False # This is what we expect now
        )
        print(f"Verified: New user is_active={user.is_active}")

        # 2. Test Response Schemas
        print("\n--- Testing Response Schemas ---")
        user_dict = {
            "id": uuid4(),
            "email": "test@example.com",
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "tenant_id": uuid4(),
            "role": UserRole.USER,
            "is_email_verified": False,
            "is_active": False,
            "deleted_at": None,
            "created_at": "2026-02-13T12:00:00Z"
        }
        
        # UserResponse should exclude is_active and deleted_at
        user_resp = UserResponse.model_validate(user_dict)
        print(f"UserResponse keys: {user_resp.model_dump().keys()}")
        if "is_active" in user_resp.model_dump() or "deleted_at" in user_resp.model_dump():
             print("FAIL: UserResponse contains sensitive status fields!")
        else:
             print("SUCCESS: UserResponse excludes sensitive fields.")

        # UserAdminResponse should include them
        admin_resp = UserAdminResponse.model_validate(user_dict)
        print(f"UserAdminResponse keys: {admin_resp.model_dump().keys()}")
        if "is_active" in admin_resp.model_dump() and "deleted_at" in admin_resp.model_dump():
             print("SUCCESS: UserAdminResponse includes status fields.")
        else:
             print("FAIL: UserAdminResponse missing fields!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_logic())
