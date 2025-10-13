# comfyvn/core/event_bus.py
# 🔄 Realtime Event Bus — WebSocket + SSE Stream Bridge
# [⚙️ Server Core Production Chat | v3.1.1 Integration Alignment]

import asyncio, json, time
from typing import Set, AsyncIterator, Dict, Any


class EventBus:
    """
    Lightweight realtime pub/sub system.
    Supports both async and safe sync publish calls for embedded server use.
    """

    def __init__(self, max_queue_size: int = 100):
        self.subscribers: Set[asyncio.Queue] = set()
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------
    # Subscription Management
    # ------------------------------------------------------------
    async def subscribe(self) -> asyncio.Queue:
        """Register a new subscriber and return its queue."""
        q: asyncio.Queue = asyncio.Queue(self._max_queue_size)
        async with self._lock:
            self.subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        """Unregister a subscriber queue."""
        async with self._lock:
            self.subscribers.discard(q)

    # ------------------------------------------------------------
    # Broadcast Utilities
    # ------------------------------------------------------------
    async def broadcast(self, event: Dict[str, Any]):
        """Send event to all subscribers asynchronously."""
        if not event:
            return
        event.setdefault("ts", int(time.time() * 1000))
        payload = json.dumps(event, ensure_ascii=False)

        async with self._lock:
            dead = []
            for q in list(self.subscribers):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    # Drop oldest message if full
                    try:
                        _ = q.get_nowait()
                        q.put_nowait(payload)
                    except Exception:
                        dead.append(q)
            for q in dead:
                self.subscribers.discard(q)

    async def heartbeat(self):
        """Periodic ping event for GUI and SSE monitors."""
        await self.broadcast({"type": "heartbeat"})

    # ------------------------------------------------------------
    # Sync Wrapper (for non-async callers)
    # ------------------------------------------------------------
    def publish(self, event: Dict[str, Any]):
        """
        Safe sync wrapper to broadcast from threads or blocking contexts.
        Used by job_manager, snapshot_api, or other sync systems.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.broadcast(event))
            else:
                loop.run_until_complete(self.broadcast(event))
        except RuntimeError:
            # In GUI threads without running loop, create new one
            asyncio.run(self.broadcast(event))
        except Exception as e:
            print(f"[EventBus] publish error: {e}")

    # ------------------------------------------------------------
    # SSE Stream Generator
    # ------------------------------------------------------------
    async def stream(self) -> AsyncIterator[str]:
        """Async generator yielding SSE formatted lines."""
        q = await self.subscribe()
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
        finally:
            await self.unsubscribe(q)
