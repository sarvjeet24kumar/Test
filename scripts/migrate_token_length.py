"""
Migration script to increase the length of token columns in the database.
"""

import asyncio
from sqlalchemy import text
from app.db.session import get_db

async def migrate():
    print("Starting database migration for token length...")
    
    # We use a database session and execute raw SQL for simplicity in this case
    async for db in get_db():
        try:
            # Alter shopping_list_invites.token
            print("Altering shopping_list_invites.token...")
            await db.execute(text("ALTER TABLE shopping_list_invites ALTER COLUMN token TYPE VARCHAR(1024);"))
            
            # Alter blacklisted_tokens.token_id
            print("Altering blacklisted_tokens.token_id...")
            await db.execute(text("ALTER TABLE blacklisted_tokens ALTER COLUMN token_id TYPE VARCHAR(1024);"))
            
            await db.commit()
            print("Migration successful.")
        except Exception as e:
            print(f"Migration failed: {e}")
            await db.rollback()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(migrate())
