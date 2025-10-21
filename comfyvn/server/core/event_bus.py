from __future__ import annotations

import collections
import threading
import time
from typing import Any, Callable, Deque, Dict, List

from PySide6.QtGui import QAction


class EventBus:
    def __init__(self, max_events: int = 500):
        self._subs: Dict[str, List[Callable[[dict], None]]] = {}
        self._lock = threading.Lock()
        self._buf: Deque[dict] = collections.deque(maxlen=max_events)

    def publish(self, topic: str, data: dict):
        evt = {"t": time.time(), "topic": topic, "data": data}
        with self._lock:
            self._buf.append(evt)
            subs = list(self._subs.get(topic, []))
        for cb in subs:
            try:
                cb(data)
            except Exception:
                pass

    def subscribe(self, topic: str, cb: Callable[[dict], None]):
        with self._lock:
            self._subs.setdefault(topic, []).append(cb)

    def recent(self, limit: int = 200):
        with self._lock:
            return list(self._buf)[-limit:]
