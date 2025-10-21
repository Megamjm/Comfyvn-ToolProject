# comfyvn/core/task_hub.py
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional


@dataclass
class TaskInfo:
    id: str
    label: str
    status: str = "queued"
    progress: float = 0.0
    cancel_cb: Optional[Callable[[], None]] = None
    meta: dict = field(default_factory=dict)


class TaskHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: Dict[str, TaskInfo] = {}

    def upsert(self, t: TaskInfo):
        with self._lock:
            self._tasks[t.id] = t

    def update(self, tid: str, **kw):
        with self._lock:
            if tid in self._tasks:
                for k, v in kw.items():
                    setattr(self._tasks[tid], k, v)

    def all(self):
        with self._lock:
            return list(self._tasks.values())

    def cancel(self, tid: str):
        with self._lock:
            t = self._tasks.get(tid)
        if t and t.cancel_cb:
            t.cancel_cb()
            self.update(tid, status="canceled")


task_hub = TaskHub()
