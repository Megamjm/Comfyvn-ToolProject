from __future__ import annotations

# comfyvn/core/shortcuts.py
from dataclasses import dataclass
from typing import List

from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget


@dataclass
class ShortcutSpec:
    seq: str
    handler_name: str
    scope: str = "global"


class ShortcutRegistry:
    def __init__(self):
        self._defs: List[ShortcutSpec] = []
        self._active: List[QShortcut] = []

    def add(self, spec: ShortcutSpec):
        self._defs.append(spec)

    def register_to(self, widget: QWidget):
        # clear old
        for s in self._active:
            try:
                s.setParent(None)
            except Exception:
                pass
        self._active.clear()
        # new
        for spec in self._defs:
            sc = QShortcut(QKeySequence(spec.seq), widget)
            fn = getattr(widget, spec.handler_name, None)
            if callable(fn):
                sc.activated.connect(fn)
            self._active.append(sc)


shortcut_registry = ShortcutRegistry()


def seed_defaults():
    for seq, fn in [
        ("Ctrl+N", "new_project"),
        ("Ctrl+S", "save_project"),
        ("Ctrl+Shift+S", "save_project_as"),
        ("Ctrl+O", "load_project"),
        ("F1", "open_dashboard"),
        ("F2", "open_assets"),
        ("F3", "open_timeline"),
        ("F4", "open_render"),
        ("F5", "open_gpu_local"),
        ("F6", "open_gpu_remote"),
        ("F7", "toggle_log_console"),
        ("Ctrl+Enter", "submit_dummy_render"),
    ]:
        shortcut_registry.add(ShortcutSpec(seq, fn))
