from __future__ import annotations
from PySide6.QtGui import QAction

import time, threading, heapq, uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

DEFAULT_QUEUE = "render"

@dataclass(order=True)
class QItem:
    due: float
    priority: int
    seq: int
    id: str = field(compare=False)
    type: str = field(compare=False)
    queue: str = field(compare=False, default=DEFAULT_QUEUE)
    device: str = field(compare=False, default="cpu")
    payload: dict = field(compare=False, default_factory=dict)

class RenderManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.q: List[QItem] = []
        self.seq = 0
        self.running = True
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()
        self.registry: Dict[str, QItem] = {}

    def enqueue(self, payload: dict) -> dict:
        """payload: {type, prompt, priority, queue, device}"""
        t = str(payload.get("type") or "image")
        prio = int(payload.get("priority") or 0)
        q = str(payload.get("queue") or DEFAULT_QUEUE)
        dev = str(payload.get("device") or "cpu")
        jid = payload.get("id") or uuid.uuid4().hex[:12]
        with self.lock:
            self.seq += 1
            qi = QItem(due=time.time(), priority=-prio, seq=self.seq,
                       id=jid, type=t, queue=q, device=dev,
                       payload=dict(payload, id=jid))
            heapq.heappush(self.q, qi)
            self.registry[jid] = qi
            self.cond.notify_all()
        return {"ok": True, "id": jid}

    def list(self) -> List[dict]:
        with self.lock:
            return [
                {"id": x.id, "type": x.type, "queue": x.queue,
                 "priority": -x.priority, "device": x.device}
                for x in sorted(self.q)
            ]

    def reprioritize(self, job_id: str, priority: int) -> dict:
        with self.lock:
            qi = self.registry.get(job_id)
            if not qi:
                return {"ok": False, "error": "not_found"}
            # rebuild heap
            for i, it in enumerate(self.q):
                if it.id == job_id:
                    self.q.pop(i)
                    heapq.heapify(self.q)
                    break
            qi.priority = -int(priority)
            self.seq += 1
            qi.seq = self.seq
            heapq.heappush(self.q, qi)
            self.cond.notify_all()
            return {"ok": True}

    def redevice(self, job_id: str, device: str) -> dict:
        with self.lock:
            qi = self.registry.get(job_id)
            if not qi:
                return {"ok": False, "error": "not_found"}
            qi.device = device
            return {"ok": True}

    def _execute(self, qi: QItem):
        # Stub: integrate ComfyUI call here in future
        time.sleep(0.05)

    def _loop(self):
        while self.running:
            with self.lock:
                if not self.q:
                    self.cond.wait(timeout=0.5)
                    continue
                qi = self.q[0]
                if qi.due > time.time():
                    self.cond.wait(timeout=max(0.02, qi.due - time.time()))
                    continue
                heapq.heappop(self.q)
            try:
                self._execute(qi)
            finally:
                with self.lock:
                    self.registry.pop(qi.id, None)

    def snapshot(self):
        with self.lock:
            return {"queued": self.list(), "running": False}

    def shutdown(self):
        self.running = False
        with self.lock:
            self.cond.notify_all()
        self.worker.join(timeout=1.0)