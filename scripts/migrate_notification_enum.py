import asyncio
from sqlalchemy import text
from app.db.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)

async def migrate_notification_enum():
    new_values = ["ITEM_UPDATED", "ITEM_DELETED", "MEMBER_REMOVED", "LIST_UPDATED"]
    
    # Use isolation_level="AUTOCOMMIT" because ALTER TYPE ... ADD VALUE cannot run in a transaction
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        
        # Check existing values
        result = await conn.execute(text(
            "SELECT enumlabel FROM pg_enum "
            "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
            "WHERE pg_type.typname = 'notification_type'"
        ))
        existing_values = {row[0] for row in result}
        
        for val in new_values:
            if val not in existing_values:
                logger.info(f"Adding {val} to notification_type enum")
                try:
                    await conn.execute(text(f"ALTER TYPE notification_type ADD VALUE '{val}'"))
                    logger.info(f"Successfully added {val}")
                except Exception as e:
                    logger.error(f"Failed to add {val}: {e}")
            else:
                logger.info(f"{val} already exists in notification_type enum")

if __name__ == "__main__":
    asyncio.run(migrate_notification_enum())
