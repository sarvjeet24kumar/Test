import asyncio
from sqlalchemy import select
from app.db.database import engine
from app.models.chat_message import ChatMessage

async def check():
    async with engine.connect() as conn:
        result = await conn.execute(select(ChatMessage).order_by(ChatMessage.created_at.desc()).limit(10))
        messages = result.all()
        print(f"Total messages found: {len(messages)}")
        for m in messages:
            print(f"List: {m.shopping_list_id}, Sender: {m.sender_id}, Content: {m.content}")

if __name__ == "__main__":
    asyncio.run(check())
