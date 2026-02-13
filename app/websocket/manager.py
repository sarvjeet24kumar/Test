"""
WebSocket Connection Manager

Manages WebSocket connections and broadcasts.
Simplified for single-server deployment (Redis Pub/Sub removed).
"""

import json
from typing import Dict, Set, Optional, List
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.shopping_list_member import ShoppingListMember
from app.models.user import User


class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.
    Supports multiple connections per user and scoped subscriptions.
    """

    def __init__(self):
        # user_id -> Dict[WebSocket, str (scope)]
        self.active_connections: Dict[str, Dict[WebSocket, str]] = {}
        # list_id -> Set of user_ids
        self.list_subscribers: Dict[str, Set[str]] = {}
        # user_id -> Set of list_ids
        self.user_subscriptions: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: str, scope: str = "global") -> None:
        """Accept a new WebSocket connection with a specific scope."""
        # Note: websocket.accept() should be called by the endpoint before/after calling this if preferred,
        # but here we assume it's already accepted or we handle it if needed.
        # To be safe, we let the endpoint handle accept() as it might need specific headers.
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = {}
            self.user_subscriptions[user_id] = set()
        
        self.active_connections[user_id][websocket] = scope

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Handle WebSocket disconnection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].pop(websocket, None)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                # Clean up subscriptions only if NO connections remain for this user
                if user_id in self.user_subscriptions:
                    for list_id in list(self.user_subscriptions[user_id]):
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

    async def broadcast_to_list(self, list_id: str, message: dict, exclude_user_id: Optional[str] = None) -> None:
        """Broadcast a message to all subscribers of a list across all their connections."""
        if list_id not in self.list_subscribers:
            return
        
        message_str = json.dumps(message)
        user_ids = list(self.list_subscribers[list_id])
        
        for user_id in user_ids:
            if exclude_user_id and user_id == exclude_user_id:
                continue

            if user_id in self.active_connections:
                dead_sockets = []
                # Create a copy of keys to avoid modification issues
                sockets = list(self.active_connections[user_id].keys())
                for ws in sockets:
                    # Filter: Only send list-scoped messages to global sockets OR the specific list socket
                    scope = self.active_connections[user_id].get(ws)
                    if scope == "global" or scope == list_id:
                        try:
                            await ws.send_text(message_str)
                        except Exception:
                            dead_sockets.append(ws)
                
                for ws in dead_sockets:
                    await self.disconnect(user_id, ws)

    async def broadcast_event(self, list_id: str, event_type: str, data: dict, exclude_user_id: Optional[str] = None) -> None:
        """Broadcast a structured event to all list subscribers."""
        # Special handling for member removal: kick the user immediately
        if event_type == "member_removed" or event_type == "member_left":
            removed_user_id = str(data.get("user_id"))
            if removed_user_id:
                await self.kick_user_from_list(removed_user_id, list_id, event_type)

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
            exclude_user_id=exclude_user_id
        )

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """Send a message to a specific user (on all their connections)."""
        if user_id not in self.active_connections or not self.active_connections[user_id]:
            return False
        
        message_str = json.dumps(message)
        dead_sockets = []
        success = False
        
        sockets = list(self.active_connections[user_id].keys())
        for ws in sockets:
            try:
                await ws.send_text(message_str)
                success = True
            except Exception:
                dead_sockets.append(ws)
        
        for ws in dead_sockets:
            await self.disconnect(user_id, ws)
            
        return success

    async def disconnect_all_for_user(self, user_id: str, reason: str = "Logged out") -> None:
        """Close ALL WebSocket connections for a specific user immediately."""
        if user_id in self.active_connections:
            # Create a copy of the socket list to avoid modification issues during iteration
            sockets = list(self.active_connections[user_id].keys())
            for ws in sockets:
                try:
                    await ws.close(code=4001, reason=reason)
                except Exception:
                    pass
                await self.disconnect(user_id, ws)

    async def kick_user_from_list(self, user_id: str, list_id: str, reason: str) -> None:
        """Kick a user from a specific list scope and close their dedicated sockets."""
        # 1. Notify them on ALL connections (so they see it in the UI)
        await self.send_to_user(user_id, {
            "type": "kicked",
            "payload": {
                "list_id": list_id,
                "reason": reason,
            },
        })

        # 2. Find and CLOSE any sockets specifically scoped to this list
        if user_id in self.active_connections:
            to_close = [
                ws for ws, scope in self.active_connections[user_id].items()
                if scope == list_id
            ]
            for ws in to_close:
                try:
                    await ws.close(code=4003, reason=f"Kicked: {reason}")
                except Exception:
                    pass
                await self.disconnect(user_id, ws)

        # 3. Remove from internal subscription registry
        await self.unsubscribe_from_list(user_id, list_id)


# Global connection manager instance
manager = ConnectionManager()
