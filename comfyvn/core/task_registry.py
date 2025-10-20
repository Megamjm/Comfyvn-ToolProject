from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/task_registry.py
# Thread-safe job/task registry with simple subscription model.

import threading, time, uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List

@dataclass
class TaskItem:
    id: str
    kind: str
    status: str = "queued"   # queued | running | done | error | canceled
    progress: float = 0.0
    message: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

class TaskRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: Dict[str, TaskItem] = {}
        self._subs: List[Callable[[TaskItem], None]] = []

    def subscribe(self, fn: Callable[[TaskItem], None]):
        with self._lock:
            self._subs.append(fn)

    def _emit(self, item: TaskItem):
        subs = []
        with self._lock:
            subs = list(self._subs)
        for s in subs:
            try: s(item)
            except Exception: pass

    def create(self, kind: str, message: str="", meta=None) -> TaskItem:
        t = TaskItem(id=str(uuid.uuid4()), kind=kind, message=message, meta=meta or {})
        with self._lock:
            self._tasks[t.id] = t
        self._emit(t)
        return t

    def update(self, tid: str, **kwargs):
        with self._lock:
            t = self._tasks.get(tid)
            if not t: return
            for k,v in kwargs.items():
                if hasattr(t, k): setattr(t, k, v)
        self._emit(t)

    def get_all(self) -> List[TaskItem]:
        with self._lock:
            return list(self._tasks.values())

task_registry = TaskRegistry()