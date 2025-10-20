from __future__ import annotations
# comfyvn/core/shortcut_registry.py
import json
from pathlib import Path
from typing import Callable, Dict
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow

SETTINGS_FILE = Path("comfyvn/data/settings.json")

DEFAULTS = {
    # File
    "new_project": "Ctrl+N",
    "save_project": "Ctrl+S",
    "save_project_as": "Ctrl+Shift+S",
    "load_project": "Ctrl+O",
    "export_to_renpy": "Ctrl+E",
    # View / Spaces
    "open_dashboard": "Ctrl+D",
    "open_assets": "Ctrl+Shift+A",
    "open_timeline": "Ctrl+T",
    "open_playground": "Ctrl+P",
    "open_render": "Ctrl+R",
    "toggle_log_console": "Ctrl+L",
    "open_gpu_local": "Ctrl+G",
    "open_gpu_remote": "Ctrl+Shift+G",
    # Tools / Server
    "start_server_manual": "Ctrl+Alt+S",
    # Editor-ish common
    "reload_scene": "F5",
}

class ShortcutRegistry:
    def __init__(self):
        self.shortcuts: Dict[str, str] = DEFAULTS.copy()
        self._callbacks: Dict[str, Callable] = {}
        self._actions: Dict[str, QAction] = {}

    def load_from_file(self):
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "shortcuts" in data and isinstance(data["shortcuts"], dict):
                    self.shortcuts.update(data["shortcuts"])
            except Exception:
                pass

    def save_to_file(self):
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps({"shortcuts": self.shortcuts}, indent=2), encoding="utf-8")

    def register(self, name: str, seq: str | None = None, fn=None):
        """Register/override a shortcut and optional callback."""
        if seq:
            self.shortcuts[name] = seq
        if fn and callable(fn):
            self._callbacks[name] = fn

    def register_many(self, mapping: dict[str, str]):
        """Register many name→sequence pairs at once."""
        for k, v in mapping.items():
            if isinstance(v, str):
                self.shortcuts[k] = v

    # --- Extension hook ---
    def register_extension_shortcuts(self, ext_id: str, items: dict[str, str], callbacks: dict[str, Callable] | None=None):
        """
        Extensions call this to register defaults (items) and optional callbacks.
        The user's settings.json can still override these later.
        """
        if isinstance(items, dict):
            for name, seq in items.items():
                if isinstance(seq, str):
                    # only set if not already customized
                    if name not in self.shortcuts:
                        self.shortcuts[name] = seq
        if callbacks:
            for name, fn in callbacks.items():
                if callable(fn):
                    self._callbacks[name] = fn

    def apply_to_window(self, win: QMainWindow):
        """Attach QActions to the window with current bindings."""
        # remove prior QAction objects we created (if any)
        for name, act in list(self._actions.items()):
            try:
                win.removeAction(act)
            except Exception:
                pass
        self._actions.clear()

        # The canonical lookup order for callbacks:
        # 1) explicit callback registered via register()
        # 2) attribute on the window with same name
        for name, seq in self.shortcuts.items():
            fn = self._callbacks.get(name) or getattr(win, name, None)
            if not callable(fn):
                continue
            try:
                act = QAction(name.replace("_", " ").title(), win)
                act.setShortcut(QKeySequence(seq))
                act.triggered.connect(fn)
                win.addAction(act)
                self._actions[name] = act
                print(f"[shortcut] {seq:>12}  → {name}")
            except Exception as e:
                print(f"[shortcut] ⚠️ Failed for {name}: {e}")

shortcut_registry = ShortcutRegistry()