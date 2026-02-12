import asyncio
from sqlalchemy import text
from app.db.database import engine

async def check_enums():
    enums = ['user_role', 'member_role', 'item_status', 'invite_status', 'notification_type']
    async with engine.connect() as conn:
        for enum_name in enums:
            result = await conn.execute(text(
                "SELECT enumlabel FROM pg_enum "
                "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                "WHERE pg_type.typname = :enum_name"
            ), {"enum_name": enum_name})
            labels = [row[0] for row in result]
            print(f"{enum_name}: {labels}")

if __name__ == "__main__":
    asyncio.run(check_enums())
