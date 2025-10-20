from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import time

from comfyvn.core.gpu_manager import get_gpu_manager

# comfyvn/core/task_registry.py
# Thread-safe job/task registry with lightweight compute annotations.


@dataclass
class TaskItem:
    id: str
    kind: str
    status: str = "queued"  # queued | running | done | error | canceled
    progress: float = 0.0
    message: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())


class TaskRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: Dict[str, TaskItem] = {}
        self._subs: List[Callable[[TaskItem], None]] = []
        self._gpu_manager = get_gpu_manager()

    # ------------------------------------------------------------------
    # Subscription helpers
    # ------------------------------------------------------------------
    def subscribe(self, fn: Callable[[TaskItem], None]) -> Callable[[TaskItem], None]:
        with self._lock:
            self._subs.append(fn)
        return fn

    def unsubscribe(self, fn: Callable[[TaskItem], None]) -> None:
        with self._lock:
            if fn in self._subs:
                self._subs.remove(fn)

    def _emit(self, item: TaskItem) -> None:
        listeners: List[Callable[[TaskItem], None]]
        with self._lock:
            listeners = list(self._subs)
        for callback in listeners:
            try:
                callback(item)
            except Exception:
                continue

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def register(
        self,
        kind: str,
        payload: Dict[str, Any],
        *,
        message: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new job and annotate it with compute policy details."""
        annotated_payload = self._gpu_manager.annotate_payload(payload)
        compute_meta = annotated_payload.get("meta", {}).get("compute_policy")
        task_meta = dict(meta or {})
        task_meta["payload"] = annotated_payload
        task_meta["compute"] = compute_meta

        task = TaskItem(
            id=str(uuid.uuid4()),
            kind=kind,
            status="queued",
            message=message,
            meta=task_meta,
        )
        with self._lock:
            self._tasks[task.id] = task
        self._emit(task)
        return task.id

    def update(self, task_id: str, **updates: Any) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.updated_at = time.time()
        self._emit(task)

    def get(self, task_id: str) -> Optional[TaskItem]:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self) -> List[TaskItem]:
        with self._lock:
            return list(self._tasks.values())


task_registry = TaskRegistry()
