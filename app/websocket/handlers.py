"""
WebSocket Event Handlers

Handles incoming WebSocket messages and routes them appropriately.
"""

import json
from typing import Optional
from uuid import UUID

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.websocket.manager import manager


class WebSocketHandler:
    """Handles WebSocket message processing."""

    def __init__(self, websocket: WebSocket, user: User, db: AsyncSession):
        self.websocket = websocket
        self.user = user
        self.db = db
        self.user_id = str(user.id)

    async def handle_message(self, message: str) -> None:
        """
        Process an incoming WebSocket message.
        
        Args:
            message: Raw message string
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            payload = data.get("payload", {})

            if msg_type == "subscribe":
                await self._handle_subscribe(payload)
            elif msg_type == "unsubscribe":
                await self._handle_unsubscribe(payload)
            elif msg_type == "ping":
                await self._handle_ping()
            else:
                await self._send_error(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            await self._send_error("Invalid JSON message")
        except Exception as e:
            await self._send_error(str(e))

    async def _handle_subscribe(self, payload: dict) -> None:
        """Handle subscribe message."""
        list_id = payload.get("list_id")
        if not list_id:
            await self._send_error("Missing list_id in subscribe payload")
            return

        # Validate UUID format
        try:
            UUID(list_id)
        except ValueError:
            await self._send_error("Invalid list_id format")
            return

        # Subscribe to list
        success = await manager.subscribe_to_list(self.user_id, list_id, self.db)
        
        if success:
            await self._send_message({
                "type": "subscribed",
                "payload": {"list_id": list_id},
            })
        else:
            await self._send_error(
                f"Cannot subscribe to list {list_id}: not a member"
            )

    async def _handle_unsubscribe(self, payload: dict) -> None:
        """Handle unsubscribe message."""
        list_id = payload.get("list_id")
        if not list_id:
            await self._send_error("Missing list_id in unsubscribe payload")
            return

        await manager.unsubscribe_from_list(self.user_id, list_id)
        await self._send_message({
            "type": "unsubscribed",
            "payload": {"list_id": list_id},
        })

    async def _handle_ping(self) -> None:
        """Handle ping message."""
        await self._send_message({"type": "pong", "payload": {}})

    async def _send_message(self, message: dict) -> None:
        """Send a message to the client."""
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception:
            pass

    async def _send_error(self, error: str) -> None:
        """Send an error message to the client."""
        await self._send_message({
            "type": "error",
            "payload": {"message": error},
        })
