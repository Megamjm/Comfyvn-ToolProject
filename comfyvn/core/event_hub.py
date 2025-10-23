"""
Lightweight event hub used by legacy APIs.

The original implementation lived in ``event_hub_v05`` and depended on the Qt
event loop.  For headless environments we provide a simple in-memory pub/sub
with history so server modules can remain active.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List

__all__ = ["EventHub"]


class EventHub:
    """Thread-safe in-memory event hub with bounded history."""

    def __init__(self, history_limit: int = 200) -> None:
        self.history_limit = max(1, int(history_limit))
        self._lock = threading.RLock()
        self._history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def publish(self, topic: str, payload: Any) -> Dict[str, Any]:
        """Publish an event and store it in the bounded history."""
        topic = str(topic or "").strip()
        if not topic:
            raise ValueError("topic is required")
        event = {
            "topic": topic,
            "timestamp": time.time(),
            "payload": payload,
        }
        with self._lock:
            bucket = self._history[topic]
            bucket.append(event)
            if len(bucket) > self.history_limit:
                del bucket[: -self.history_limit]
        return {"ok": True, "count": len(self._history[topic])}

    def history(
        self, topic: str, since: float | None = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        topic = str(topic or "").strip()
        if not topic:
            return []
        since = since or 0.0
        limit = max(1, min(int(limit), self.history_limit))
        with self._lock:
            bucket: Iterable[Dict[str, Any]] = list(self._history.get(topic) or [])
        return [event for event in bucket if event["timestamp"] >= since][-limit:]
