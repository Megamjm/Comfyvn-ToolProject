from __future__ import annotations
from PySide6.QtGui import QAction
import time
from typing import Dict
from collections import defaultdict
from dataclasses import dataclass, field
try:
    from comfyvn.server.core.metrics import WS_CONN  # optional
except Exception:
    WS_CONN = None

@dataclass
class Client:
    ws: any
    user_id: str
    user_name: str
    last_seen: float = field(default_factory=lambda: time.time())

class Hub:
    def __init__(self):
        self.rooms: dict[str, dict[str, Client]] = defaultdict(dict)
        self.locks: dict[str, tuple[str, float]] = {}
        self.ttl = 30

    def join(self, scene_id: str, client: Client):
        self.rooms[scene_id][client.user_id] = client
        try: WS_CONN and WS_CONN.labels(scene=scene_id).inc()
        except Exception: pass

    def leave(self, scene_id: str, user_id: str):
        if scene_id in self.rooms and user_id in self.rooms[scene_id]:
            del self.rooms[scene_id][user_id]
            if not self.rooms[scene_id]: del self.rooms[scene_id]
        try: WS_CONN and WS_CONN.labels(scene=scene_id).dec()
        except Exception: pass

    def presence(self, scene_id: str):
        now = time.time()
        items = [{"user_id": uid, "user_name": c.user_name, "last_seen": c.last_seen} for uid, c in self.rooms.get(scene_id, {}).items()]
        lock = self.locks.get(scene_id)
        return {"now": now, "participants": items, "lock": {"owner": lock[0], "expires": lock[1]} if lock else None}

    def acquire_lock(self, scene_id: str, user_id: str, ttl: int | None = None) -> bool:
        now = time.time()
        ttl = int(ttl or self.ttl)
        owner = self.locks.get(scene_id)
        if owner and owner[1] > now and owner[0] != user_id:
            return False
        self.locks[scene_id] = (user_id, now + ttl)
        return True

    def release_lock(self, scene_id: str, user_id: str) -> bool:
        owner = self.locks.get(scene_id)
        if not owner: return True
        if owner[0] == user_id or owner[1] < time.time():
            self.locks.pop(scene_id, None); return True
        return False

HUB = Hub()