"""
WebSocket Connection Manager

Manages WebSocket connections and broadcasts.
"""

import asyncio
import json
from typing import Dict, Set, Optional
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.shopping_list_member import ShoppingListMember
from app.models.user import User
from app.services.redis_service import RedisService


class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.
    
    Connections are organized by list_id for efficient broadcasting.
    Redis pub/sub is used for cross-instance communication.
    """

    def __init__(self):
        # user_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # list_id -> Set of user_ids
        self.list_subscribers: Dict[str, Set[str]] = {}
        # user_id -> Set of list_ids
        self.user_subscriptions: Dict[str, Set[str]] = {}
        # Background task for Redis listener
        self._redis_listener_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, user: User) -> None:
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            user: Authenticated user
        """
        await websocket.accept()
        user_id = str(user.id)
        
        # Close existing connection if any
        if user_id in self.active_connections:
            old_ws = self.active_connections[user_id]
            try:
                await old_ws.close(code=4001, reason="New connection opened")
            except Exception:
                pass
        
        self.active_connections[user_id] = websocket
        self.user_subscriptions[user_id] = set()

    async def disconnect(self, user_id: str) -> None:
        """
        Handle WebSocket disconnection.
        
        Args:
            user_id: ID of the disconnected user
        """
        # Remove from active connections
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        
        # Unsubscribe from all lists
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
        """
        Subscribe a user to a shopping list's updates.
        
        Args:
            user_id: User's ID
            list_id: Shopping list ID
            db: Database session
        
        Returns:
            bool: True if subscription successful
        """
        # Verify membership
        result = await db.execute(
            select(ShoppingListMember).where(
                and_(
                    ShoppingListMember.shopping_list_id == UUID(list_id),
                    ShoppingListMember.user_id == UUID(user_id),
                )
            )
        )
        membership = result.scalar_one_or_none()
        
        if not membership:
            return False
        
        # Add to subscribers
        if list_id not in self.list_subscribers:
            self.list_subscribers[list_id] = set()
        self.list_subscribers[list_id].add(user_id)
        
        if user_id not in self.user_subscriptions:
            self.user_subscriptions[user_id] = set()
        self.user_subscriptions[user_id].add(list_id)
        
        return True

    async def unsubscribe_from_list(self, user_id: str, list_id: str) -> None:
        """
        Unsubscribe a user from a shopping list's updates.
        
        Args:
            user_id: User's ID
            list_id: Shopping list ID
        """
        if list_id in self.list_subscribers:
            self.list_subscribers[list_id].discard(user_id)
            if not self.list_subscribers[list_id]:
                del self.list_subscribers[list_id]
        
        if user_id in self.user_subscriptions:
            self.user_subscriptions[user_id].discard(list_id)

    async def broadcast_to_list(self, list_id: str, message: dict) -> None:
        """
        Broadcast a message to all subscribers of a list.
        
        Args:
            list_id: Shopping list ID
            message: Message to broadcast
        """
        if list_id not in self.list_subscribers:
            return
        
        message_str = json.dumps(message)
        dead_connections = []
        
        for user_id in self.list_subscribers[list_id]:
            if user_id in self.active_connections:
                try:
                    await self.active_connections[user_id].send_text(message_str)
                except Exception:
                    dead_connections.append(user_id)
        
        # Clean up dead connections
        for user_id in dead_connections:
            await self.disconnect(user_id)

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """
        Send a message to a specific user.
        
        Args:
            user_id: User's ID
            message: Message to send
        
        Returns:
            bool: True if sent successfully
        """
        if user_id not in self.active_connections:
            return False
        
        try:
            message_str = json.dumps(message)
            await self.active_connections[user_id].send_text(message_str)
            return True
        except Exception:
            await self.disconnect(user_id)
            return False

    async def kick_user_from_list(self, user_id: str, list_id: str, reason: str) -> None:
        """
        Kick a user from a list (e.g., when removed by owner).
        
        Args:
            user_id: User's ID
            list_id: Shopping list ID
            reason: Reason for kicking
        """
        # Send kick message
        message = {
            "type": "kicked",
            "payload": {
                "list_id": list_id,
                "reason": reason,
            },
        }
        await self.send_to_user(user_id, message)
        
        # Unsubscribe from list
        await self.unsubscribe_from_list(user_id, list_id)

    async def start_redis_listener(self) -> None:
        """Start listening for Redis pub/sub messages."""
        if self._redis_listener_task is not None:
            return
        
        self._redis_listener_task = asyncio.create_task(self._redis_listener())

    async def stop_redis_listener(self) -> None:
        """Stop the Redis listener."""
        if self._redis_listener_task:
            self._redis_listener_task.cancel()
            try:
                await self._redis_listener_task
            except asyncio.CancelledError:
                pass
            self._redis_listener_task = None

    async def _redis_listener(self) -> None:
        """Listen for Redis pub/sub messages and broadcast to WebSocket clients."""
        try:
            client = await RedisService.get_client()
            pubsub = client.pubsub()
            
            # Subscribe to pattern for all list channels
            await pubsub.psubscribe("list:*")
            
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    try:
                        channel = message["channel"]
                        if isinstance(channel, bytes):
                            channel = channel.decode()
                        
                        # Extract list_id from channel (list:{list_id})
                        list_id = channel.split(":", 1)[1]
                        
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode()
                        
                        event = json.loads(data)
                        
                        # Handle member_removed event specially
                        if event.get("event") == "member_removed":
                            user_id = event["data"]["user_id"]
                            await self.kick_user_from_list(
                                user_id, list_id, "removed_by_owner"
                            )
                        
                        # Broadcast to all list subscribers
                        await self.broadcast_to_list(list_id, {
                            "type": "event",
                            "payload": event,
                        })
                        
                    except Exception as e:
                        print(f"Error processing Redis message: {e}")
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Redis listener error: {e}")


# Global connection manager instance
manager = ConnectionManager()
