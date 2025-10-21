from __future__ import annotations

from threading import RLock
# comfyvn/core/workspace_bus.py
# [COMFYVN Architect | v1.0 | this chat]
from typing import Any, Callable, Dict, Optional

from PySide6.QtGui import QAction

from comfyvn.core.core import hooks


class WorkspaceBus:
    """Shared context across panels (project, selection, modes)."""

    def __init__(self):
        self._lock = RLock()
        self._state: Dict[str, Any] = {
            "project": None,
            "scene": None,
            "character": None,
        }

    def set(self, key: str, value: Any):
        with self._lock:
            self._state[key] = value
        hooks.emit("workspace.changed", key, value)

    def get(self, key: str, default=None):
        with self._lock:
            return self._state.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)


bus = WorkspaceBus()
