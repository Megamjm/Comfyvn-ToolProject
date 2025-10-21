# comfyvn/core/event_bus.py
# [COMFYVN Architect | v1.3 | this chat]
import threading
from typing import Any, Callable, Dict, List

from PySide6.QtGui import QAction

_lock = threading.Lock()
_subs: Dict[str, List[Callable[[Any], None]]] = {}


def subscribe(event: str, fn: Callable[[Any], None]):
    with _lock:
        _subs.setdefault(event, []).append(fn)


def unsubscribe(event: str, fn: Callable[[Any], None]):
    with _lock:
        if event in _subs and fn in _subs[event]:
            _subs[event].remove(fn)
            if not _subs[event]:
                _subs.pop(event, None)


def emit(event: str, data=None):
    with _lock:
        listeners = list(_subs.get(event, []))
    for cb in listeners:
        try:
            cb(data)
        except Exception as e:
            print(f"[event_bus] handler error for {event}: {e}")
