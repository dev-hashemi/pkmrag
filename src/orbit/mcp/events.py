"""Real-time Server-Sent Events (SSE) broadcaster for vault changes and reindex events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any


class EventBroadcaster:
    """In-memory async publish/subscribe broker for Server-Sent Events."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()

    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast an event payload to all currently connected SSE clients."""
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> AsyncIterator[str]:
        """Subscribe to the broadcaster and yield formatted SSE messages until disconnected."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)

        try:
            # Yield initial connection confirmation
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
            while True:
                try:
                    # Timeout after 15s to send keep-alive comment
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            async with self._lock:
                self._subscribers.discard(queue)
