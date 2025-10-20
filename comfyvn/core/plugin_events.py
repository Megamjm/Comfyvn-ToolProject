from __future__ import annotations
from PySide6.QtGui import QAction
from typing import Any
from comfyvn.ext.plugins import PluginManager

def dispatch(pm: PluginManager, topic: str, payload: dict):
    for plug in getattr(pm, "plugins", []):
        fn = getattr(plug, "on_event", None)
        if callable(fn):
            try:
                fn(topic, payload)
            except Exception:
                pass