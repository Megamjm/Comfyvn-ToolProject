from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class _Subscriber:
    topics: Optional[Set[str]]
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop


class AsyncEventHub:
    """Thread-safe publish/subscribe hub backed by asyncio queues."""

    def __init__(self, *, queue_size: int = 256) -> None:
        self._queue_size = max(1, int(queue_size))
        self._lock = threading.RLock()
        self._subscribers: Tuple[_Subscriber, ...] = ()

    async def subscribe(self, topics: Optional[Sequence[str]] = None) -> asyncio.Queue:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        normalised = self._normalise(topics)
        subscriber = _Subscriber(normalised, queue, loop)
        with self._lock:
            self._subscribers = self._subscribers + (subscriber,)
        return queue

    def unsubscribe(
        self, queue: asyncio.Queue, topics: Optional[Sequence[str]] = None
    ) -> None:
        with self._lock:
            self._subscribers = tuple(
                sub for sub in self._subscribers if sub.queue is not queue
            )

    def publish(self, topic: str, payload: Any) -> None:
        topic_name = str(topic or "").strip()
        if not topic_name:
            return
        event = {
            "topic": topic_name,
            "timestamp": time.time(),
            "payload": payload,
        }
        with self._lock:
            subscribers = self._subscribers
        for sub in subscribers:
            if sub.topics is not None and topic_name not in sub.topics:
                continue
            sub.loop.call_soon_threadsafe(self._push, sub.queue, event)

    def _push(self, queue: asyncio.Queue, event: dict[str, Any]) -> None:
        try:
            while queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            queue.put_nowait(event)
        except Exception:
            # If the consumer disappeared mid-flight we silently drop the event.
            pass

    @staticmethod
    def _normalise(
        topics: Optional[Sequence[str]],
    ) -> Optional[Set[str]]:
        if not topics:
            return None
        items = {str(topic).strip() for topic in topics if str(topic).strip()}
        if "*" in items:
            return None
        return items or None
