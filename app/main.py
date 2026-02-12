"""
MiniMart FastAPI Application

Main application entry point with all configurations.
"""

from contextlib import asynccontextmanager
from uuid import UUID
from typing import Annotated

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError

from app.core.config import settings
from app.db.database import init_db, close_db, engine
from app.db.session import get_db
from app.api import api_router
from app.core.security import decode_token
from app.exceptions.handlers import setup_exception_handlers
from app.exceptions.base import MiniMartException
from app.models.user import User
from app.websocket.manager import manager
from app.websocket.handlers import WebSocketHandler
from app.services.redis_service import RedisService
from sqlalchemy import select


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("Starting MiniMart API...")
    
    # Initialize database tables (for development)
    if settings.is_development:
        await init_db()
    
    yield
    
    # Shutdown
    print("Shutting down MiniMart API...")
    await RedisService.close()
    await close_db()


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Multi-tenant shopping list application with real-time synchronization",
    version="1.0.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# Setup exception handlers
setup_exception_handlers(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API router
app.include_router(api_router)


# Health check endpoints
@app.get("/health", tags=["Health"])
async def health_check():
    """Basic liveness check."""
    return {"success": True, "data": {"status": "healthy", "app": settings.app_name}}


@app.get("/health/ready", tags=["Health"])
async def readiness_check(db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Readiness check including database and Redis connectivity.
    """
    errors = []
    
    # Check database
    try:
        await db.execute(select(1))
    except Exception as e:
        errors.append(f"Database: {str(e)}")
    
    # Check Redis
    try:
        client = await RedisService.get_client()
        await client.ping()
    except Exception as e:
        errors.append(f"Redis: {str(e)}")
    
    if errors:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": {"code": "UNHEALTHY", "message": "Service unhealthy", "details": {"errors": errors}}},
        )
    
    return {"success": True, "data": {"status": "ready"}}


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint for real-time updates.
    
    Query parameters:
    - token: JWT access token
    
    Message format:
    - Subscribe: {"type": "subscribe", "payload": {"list_id": "uuid"}}
    - Unsubscribe: {"type": "unsubscribe", "payload": {"list_id": "uuid"}}
    - Ping: {"type": "ping"}
    """
    # Authenticate
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token type")
            return
        
        user_id = payload.get("sub")
        result = await db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            await websocket.close(code=4001, reason="User not found or inactive")
            return
        
    except JWTError as e:
        await websocket.close(code=4001, reason=f"Invalid token: {str(e)}")
        return
    
    # Connect
    await manager.connect(websocket, user)
    handler = WebSocketHandler(websocket, user, db)
    
    try:
        # Send connection confirmation
        await websocket.send_text('{"type": "connected", "payload": {}}')
        
        # Message loop
        while True:
            message = await websocket.receive_text()
            await handler.handle_message(message)
            
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(str(user.id), websocket)


# ==================== Chat WebSocket Endpoint ====================


@app.websocket("/ws/shopping-lists/{list_id}/chat")
async def chat_websocket_endpoint(
    websocket: WebSocket,
    list_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Dedicated WebSocket endpoint for list-scoped real-time chat.

    Connect:  ws://host/ws/shopping-lists/{list_id}/chat?token=<JWT>
    Send:     {"type": "chat_message", "message": "Hello"}
    Receive:  {"type": "chat_message", "id": "uuid", ...}
    """
    import json as _json
    from app.services.chat_service import ChatService

    # 1. Authenticate
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token type")
            return

        user_id = payload.get("sub")
        result = await db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            await websocket.close(code=4001, reason="User not found or inactive")
            return

    except JWTError as e:
        await websocket.close(code=4001, reason=f"Invalid token: {str(e)}")
        return

    # 2. Validate membership & Subscribe
    try:
        list_uuid = UUID(list_id)
    except ValueError:
        await websocket.close(code=4003, reason="Invalid list_id format")
        return

    # Use manager to connect and subscribe
    await manager.connect(websocket, user)
    subscribed = await manager.subscribe_to_list(str(user.id), list_id, db)
    if not subscribed:
        await manager.disconnect(str(user.id), websocket)
        await websocket.close(code=4003, reason="Not a member of this list")
        return

    chat_service = ChatService(db)
    try:
        # Send connection confirmation
        await websocket.send_text(_json.dumps({
            "type": "connected",
            "payload": {"list_id": list_id},
        }))

        # 4. Message loop
        while True:
            raw = await websocket.receive_text()

            try:
                data = _json.loads(raw)
            except _json.JSONDecodeError:
                await websocket.send_text(_json.dumps({
                    "type": "error",
                    "payload": {"message": "Invalid JSON"},
                }))
                continue

            msg_type = data.get("type")

            if msg_type == "chat_message":
                content = data.get("message", "").strip()
                if not content:
                    await websocket.send_text(_json.dumps({
                        "type": "error",
                        "payload": {"message": "Message content cannot be empty"},
                    }))
                    continue

                # Re-validate membership on every send
                try:
                    await chat_service._verify_membership(list_uuid, user)
                except Exception as e:
                    await websocket.send_text(_json.dumps({
                        "type": "error",
                        "payload": {"message": "You are no longer a member of this list"},
                    }))
                    continue

                # Persist & Broadcast is handled by the service
                try:
                    await chat_service.send_message(list_uuid, user, content)
                except Exception as e:
                    print(f"Chat WS: Error in send_message: {e}")
                    await websocket.send_text(_json.dumps({
                        "type": "error",
                        "payload": {"message": f"Server error: {str(e)}"},
                    }))
                    continue

            elif msg_type == "ping":
                await websocket.send_text(_json.dumps({"type": "pong", "payload": {}}))

            else:
                await websocket.send_text(_json.dumps({
                    "type": "error",
                    "payload": {"message": f"Unknown message type: {msg_type}"},
                }))

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(str(user.id), websocket)


# Run with: uvicorn app.main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
    )
