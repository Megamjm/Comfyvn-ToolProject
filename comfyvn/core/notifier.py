from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/notifier.py
# [COMFYVN Architect | v1.0 | this chat]
from typing import Callable, List, Dict
from time import time

class Notifier:
    def __init__(self):
        self.history: List[Dict] = []
        self.enabled = True
        self._listeners: List[Callable[[Dict], None]] = []
        self._max_history = 200

    def attach(self, callback: Callable[[Dict], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def toast(self, level: str, msg: str, *, meta: Dict | None = None):
        evt = {"ts": time(), "level": level, "msg": msg, "meta": meta or {}}
        self.history.append(evt)
        if len(self.history) > self._max_history:
            self.history = self.history[-self._max_history :]
        print(f"[TOAST] {level}: {msg}")
        for callback in list(self._listeners):
            try:
                callback(evt)
            except Exception:
                pass

    def list(self):
        return list(self.history)

notifier = Notifier()
