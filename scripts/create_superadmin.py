import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.core.security import hash_password
from app.core.config import settings


async def create_superadmin():
    engine = create_async_engine(settings.database_url)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as db:
        # Check if Super Admin already exists
        result = await db.execute(select(User).where(User.username == "admin"))
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            print("Creating Global Super Admin User...")
            admin_user = User(
                tenant_id=None,  # Super Admin is global
                first_name="Super",
                last_name="Admin",
                username="admin",
                email="admin1@yopmail.com",
                password=hash_password("Set@1234"),
                role=UserRole.SUPER_ADMIN,
                is_email_verified=True,
                is_active=True,
            )
            db.add(admin_user)
            print("Super Admin created.")
        else:
            print("Updating existing Super Admin to be Global (tenant_id=None)...")
            admin_user.tenant_id = None
            admin_user.password = hash_password("admin1234")
            admin_user.role = UserRole.SUPER_ADMIN
            print("User updated.")

        await db.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_superadmin())
