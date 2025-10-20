from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/extension_gui_bridge.py
import json, time
from pathlib import Path
from typing import List, Dict, Any, Optional

from comfyvn.core.extension_runtime import runtime
from comfyvn.core.task_registry import task_registry

# Optional manifest watcher for "restart required" notifications
class ExtensionGuiBridge:
    def __init__(self, exts_dir: str = "extensions"):
        self.exts_dir = Path(exts_dir)
        self._mtimes: Dict[str, float] = {}
        self._restart_needed = False
        self._state_file = Path("comfyvn/data/_runtime_state.json")

    # ---- Discovery / Load ------------------------------------------------
    def discover(self) -> List[dict]:
        # Delegate to runtime - it already knows how
        return runtime.discover()

    def load_enabled(self, ctx: Optional[dict] = None):
        runtime.load_all(ctx)

    def unload_all(self, ctx: Optional[dict] = None):
        runtime.unload_all(ctx)

    def reload_all(self, ctx: Optional[dict] = None):
        runtime.unload_all(ctx)
        runtime.load_all(ctx)

    # ---- State persistence -----------------------------------------------
    def save_state(self):
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "ts": time.time(),
                "tasks": task_registry.list(),
                "exts": [e.get("name") for e in runtime.extensions or []]
            }
            self._state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def resume_state(self):
        try:
            if self._state_file.exists():
                # In practice, you'd re-enqueue tasks here.
                # We just acknowledge presence.
                return json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    # ---- Restart flagging ------------------------------------------------
    def needs_restart(self) -> bool:
        return bool(self._restart_needed)

    def mark_restart_needed(self):
        self._restart_needed = True

    def clear_restart_flag(self):
        self._restart_needed = False

    # ---- Info for GUI ----------------------------------------------------
    def info(self) -> dict:
        exts = []
        for e in (runtime.extensions or []):
            exts.append({
                "name": e.get("name"),
                "version": e.get("version"),
                "enabled": bool(e.get("enabled", True)),
                "entry": e.get("entry"),
                "reload_required": bool(e.get("reload_required", False)),
                "persistent": bool(e.get("persistent", False)),
                "description": e.get("description", "")
            })
        return {
            "restart_needed": self._restart_needed,
            "extensions": exts,
            "tasks": task_registry.list(),
        }

bridge = ExtensionGuiBridge()