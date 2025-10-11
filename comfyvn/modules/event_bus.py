# comfyvn/modules/event_bus.py
# 🔄 Realtime Event Bus – WebSocket + SSE Stream (Patch H)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import asyncio, json, time
from typing import Set, AsyncIterator

class EventBus:
    """Lightweight pub/sub system using per-subscriber asyncio.Queue."""

    def __init__(self, max_queue_size: int = 100):
        self._subscribers: Set[asyncio.Queue] = set()
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()

    # -------------------------------------------------
    # Subscription Management
    # -------------------------------------------------
    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(self._max_queue_size)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        async with self._lock:
            self._subscribers.discard(q)

    # -------------------------------------------------
    # Broadcast & Heartbeat
    # -------------------------------------------------
    async def broadcast(self, event: dict):
        """Send event to all subscribers as a JSON string."""
        event.setdefault("ts", int(time.time() * 1000))
        payload = json.dumps(event, ensure_ascii=False)

        async with self._lock:
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    # drop oldest then retry
                    try:
                        _ = q.get_nowait()
                        q.put_nowait(payload)
                    except Exception:
                        dead.append(q)
            for q in dead:
                self._subscribers.discard(q)

    async def heartbeat(self):
        """Send periodic heartbeat event."""
        await self.broadcast({"type": "heartbeat"})

    # -------------------------------------------------
    # SSE Stream Generator
    # -------------------------------------------------
    async def stream(self) -> AsyncIterator[str]:
        """
        Async generator yielding events as SSE lines.
        Example: used in /sse/jobs endpoint.
        """
        q = await self.subscribe()
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
        finally:
            await self.unsubscribe(q)
