"""
WebSocket Connection Manager

Manages WebSocket connections and broadcasts.
Simplified for single-server deployment (Redis Pub/Sub removed).
"""

import json
from typing import Dict, Set, Optional
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.shopping_list_member import ShoppingListMember
from app.models.user import User


class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.
    Supports multiple connections per user (e.g., from multiple tabs or global/dedicated sockets).
    """

    def __init__(self):
        # user_id -> Set of WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # list_id -> Set of user_ids
        self.list_subscribers: Dict[str, Set[str]] = {}
        # user_id -> Set of list_ids
        self.user_subscriptions: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, user: User) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        user_id = str(user.id)
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
            self.user_subscriptions[user_id] = set()
        
        self.active_connections[user_id].add(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Handle WebSocket disconnection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                # Clean up subscriptions only if NO connections remain for this user
                if user_id in self.user_subscriptions:
                    for list_id in self.user_subscriptions[user_id]:
                        if list_id in self.list_subscribers:
                            self.list_subscribers[list_id].discard(user_id)
                            if not self.list_subscribers[list_id]:
                                del self.list_subscribers[list_id]
                    del self.user_subscriptions[user_id]

    async def subscribe_to_list(
        self, user_id: str, list_id: str, db: AsyncSession
    ) -> bool:
        """Subscribe a user to a shopping list's updates."""
        result = await db.execute(
            select(ShoppingListMember).where(
                and_(
                    ShoppingListMember.shopping_list_id == UUID(list_id),
                    ShoppingListMember.user_id == UUID(user_id),
                    ShoppingListMember.deleted_at.is_(None),
                )
            )
        )
        membership = result.scalar_one_or_none()
        
        if not membership:
            return False
        
        if list_id not in self.list_subscribers:
            self.list_subscribers[list_id] = set()
        self.list_subscribers[list_id].add(user_id)
        
        if user_id not in self.user_subscriptions:
            self.user_subscriptions[user_id] = set()
        self.user_subscriptions[user_id].add(list_id)
        
        return True

    async def unsubscribe_from_list(self, user_id: str, list_id: str) -> None:
        """Unsubscribe a user from a shopping list's updates."""
        if list_id in self.list_subscribers:
            self.list_subscribers[list_id].discard(user_id)
            if not self.list_subscribers[list_id]:
                del self.list_subscribers[list_id]
        
        if user_id in self.user_subscriptions:
            self.user_subscriptions[user_id].discard(list_id)

    async def broadcast_to_list(self, list_id: str, message: dict) -> None:
        """Broadcast a message to all subscribers of a list across all their connections."""
        if list_id not in self.list_subscribers:
            print(f"Manager: No subscribers for list {list_id}")
            return
        
        message_str = json.dumps(message)
        user_ids = list(self.list_subscribers[list_id])
        print(f"Manager: Broadcasting to {len(user_ids)} users for list {list_id}")
        
        for user_id in user_ids:
            if user_id in self.active_connections:
                sockets = list(self.active_connections[user_id])
                print(f"Manager: Sending to {len(sockets)} sockets for user {user_id}")
                dead_sockets = []
                for ws in sockets:
                    try:
                        await ws.send_text(message_str)
                    except Exception as e:
                        print(f"Manager: Failed to send to socket for user {user_id}: {e}")
                        dead_sockets.append(ws)
                
                for ws in dead_sockets:
                    await self.disconnect(user_id, ws)

    async def broadcast_event(self, list_id: str, event_type: str, data: dict) -> None:
        """Broadcast a structured event to all list subscribers."""
        if event_type == "member_removed":
            removed_user_id = data.get("user_id")
            if removed_user_id:
                await self.kick_user_from_list(removed_user_id, list_id, "removed_by_owner")

        await self.broadcast_to_list(
            list_id,
            {
                "type": "event",
                "payload": {
                    "event": event_type,
                    "list_id": list_id,
                    "data": data,
                },
            },
        )

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """Send a message to a specific user (on all their connections)."""
        if user_id not in self.active_connections or not self.active_connections[user_id]:
            return False
        
        message_str = json.dumps(message)
        dead_sockets = []
        success = False
        
        for ws in list(self.active_connections[user_id]):
            try:
                await ws.send_text(message_str)
                success = True
            except Exception:
                dead_sockets.append(ws)
        
        for ws in dead_sockets:
            await self.disconnect(user_id, ws)
            
        return success

    async def kick_user_from_list(self, user_id: str, list_id: str, reason: str) -> None:
        """Kick a user from a list and notify them."""
        message = {
            "type": "kicked",
            "payload": {
                "list_id": list_id,
                "reason": reason,
            },
        }
        await self.send_to_user(user_id, message)
        await self.unsubscribe_from_list(user_id, list_id)


# Global connection manager instance
manager = ConnectionManager()
