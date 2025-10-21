# comfyvn/core/hooks.py
# [COMFYVN Architect | v1.2 | this chat]
import threading
from typing import Callable, Dict, List

from PySide6.QtGui import QAction

_lock = threading.Lock()
_registry: Dict[str, List[Callable]] = {}


def register(event: str, callback: Callable):
    with _lock:
        _registry.setdefault(event, []).append(callback)


def unregister(event: str, callback: Callable):
    with _lock:
        if event in _registry and callback in _registry[event]:
            _registry[event].remove(callback)
            if not _registry[event]:
                _registry.pop(event, None)


def emit(event: str, *args, **kwargs):
    with _lock:
        listeners = list(_registry.get(event, []))
    for cb in listeners:
        try:
            cb(*args, **kwargs)
        except Exception as e:
            print(f"[HOOKS] error in {event}: {e}")


def clear(event: str | None = None):
    with _lock:
        if event:
            _registry.pop(event, None)
        else:
            _registry.clear()
