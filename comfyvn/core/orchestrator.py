import threading
import time
from collections import deque

from PySide6.QtGui import QAction


class Orchestrator:
    """Minimal central coordinator.
    - queue: generic orchestration work units
    - tick(): runs lightweight maintenance each second via app hook
    """

    def __init__(self):
        self.queue = deque()
        self.last_tick = 0
        self.lock = threading.Lock()
        self.stats = {
            "ticks": 0,
            "dispatched": 0,
            "queue_len": 0,
        }

    def enqueue(self, item: dict):
        with self.lock:
            self.queue.append(item)
            self.stats["queue_len"] = len(self.queue)
        return {"ok": True, "queued": True, "len": self.stats["queue_len"]}

    def drain_once(self, app):
        """Dispatch one unit per tick. Integrate with render/job managers if present."""
        with self.lock:
            if not self.queue:
                return None
            item = self.queue.popleft()
            self.stats["queue_len"] = len(self.queue)
        try:
            kind = item.get("type")
            if kind == "render":
                rm = getattr(app.state, "render_manager", None)
                if rm and hasattr(rm, "enqueue"):
                    rm.enqueue(item)
                    self.stats["dispatched"] += 1
                    return {"dispatched": "render", "id": item.get("id")}
            self.stats["dispatched"] += 1
            return {"dispatched": "noop"}
        except Exception:
            return {"dispatched": "error"}

    def summary(self):
        return {
            "ok": True,
            "queue": self.stats["queue_len"],
            "ticks": self.stats["ticks"],
            "dispatched": self.stats["dispatched"],
            "last_tick": self.last_tick,
        }

    def tick(self, app):
        now = int(time.time())
        if now == self.last_tick:
            return
        self.last_tick = now
        self.drain_once(app)
        self.stats["ticks"] += 1
