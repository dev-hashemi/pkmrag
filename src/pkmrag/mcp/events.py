"""Real-time Server-Sent Events (SSE) broadcaster for vault changes and reindex events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any


class EventBroadcaster:
    """In-memory async publish/subscribe broker for Server-Sent Events."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str | None]] = set()
        self._lock = asyncio.Lock()
        self._closed = False

    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast an event payload to all currently connected SSE clients."""
        if self._closed:
            return
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def close(self) -> None:
        """Close broadcaster and notify all subscribers to end their streams."""
        async with self._lock:
            self._closed = True
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for queue in subscribers:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> AsyncIterator[str]:
        """Subscribe to the broadcaster and yield formatted SSE messages until disconnected."""
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=100)
        async with self._lock:
            if self._closed:
                return
            self._subscribers.add(queue)

        try:
            # Yield initial connection confirmation
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
            while not self._closed:
                try:
                    # Timeout after 15s to send keep-alive comment
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if msg is None:
                        break
                    yield msg
                except asyncio.TimeoutError:
                    if self._closed:
                        break
                    yield ": keep-alive\n\n"
        finally:
            async with self._lock:
                self._subscribers.discard(queue)
