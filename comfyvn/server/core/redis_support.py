import json
import os
import queue
import threading
import time
from pathlib import Path

from PySide6.QtGui import QAction

try:
    import redis as _redis  # type: ignore
except Exception:
    _redis = None

REDIS_URL = os.getenv("REDIS_URL", "").strip() or ""


class InMemoryQueue:
    def __init__(self):
        self.q = queue.Queue()

    def put(self, item: dict):
        self.q.put(json.dumps(item))

    def get(self, timeout: float = 0.1):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None


class RedisQueue:
    def __init__(self, key="comfyvn:jobs"):
        self.key = key
        if REDIS_URL and _redis:
            self.cl = _redis.from_url(REDIS_URL, decode_responses=True)
        else:
            self.cl = None
            self.mem = InMemoryQueue()

    def put(self, item: dict):
        s = json.dumps(item)
        if self.cl:
            self.cl.lpush(self.key, s)
        else:
            self.mem.put(item)

    def get(self, timeout=1.0):
        if self.cl:
            r = self.cl.brpop(self.key, timeout=max(1, int(timeout)))
            if r:
                return r[1]
            return None
        else:
            return self.mem.get(timeout=timeout)


class RedisEventsBridge:
    def __init__(self, event_bus, dir_path: str = "./data/jobs"):
        self.event_bus = event_bus
        self.dir = Path(dir_path)
        self.dir.mkdir(parents=True, exist_ok=True)

    def pump_once(self, limit=1000):
        # bridge files from data/jobs/ to event_bus handlers
        files = sorted(self.dir.glob("*.json"))[:100]
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self.event_bus.emit("job_event", data)
            finally:
                try:
                    f.unlink()
                except Exception:
                    pass
