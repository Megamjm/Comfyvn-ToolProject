from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtGui import QAction

EventHandler = Callable[[str, dict], None]
JobHandler = Callable[[dict, Optional[str]], dict]


@dataclass
class Plugin:
    name: str
    on_event: Optional[EventHandler] = None
    jobs: Dict[str, JobHandler] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


class PluginManager:
    def __init__(self):
        self.plugins: List[Plugin] = []
        self.job_handlers: Dict[str, JobHandler] = {}
        self.event_handlers: List[EventHandler] = []
        self._user_plugin_names: set[str] = set()

    def register(self, plugin: Plugin, user: bool = False):
        self.plugins.append(plugin)
        if user:
            self._user_plugin_names.add(plugin.name)
        for t, fn in (plugin.jobs or {}).items():
            self.job_handlers[t] = fn
        if plugin.on_event:
            self.event_handlers.append(plugin.on_event)

    def emit(self, kind: str, payload: dict):
        for h in list(self.event_handlers):
            try:
                h(kind, payload)
            except Exception:
                pass

    def handle(self, typ: str, payload: dict, job_id: Optional[str]):
        fn = self.job_handlers.get(typ)
        if not fn:
            return {"ok": False, "error": f"no handler for {typ}"}
        try:
            return fn(payload, job_id)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def load_from_dir(self, path: str = "./data/plugins"):
        d = Path(path)
        if not d.exists():
            return
        for p in d.glob("*.py"):
            self._load_file(p, user=True)

    def _load_file(self, p: Path, user: bool):
        try:
            spec = importlib.util.spec_from_file_location(p.stem, p)
            mod = importlib.util.module_from_spec(spec)  # type: ignore
            sys.modules[p.stem] = mod
            assert spec and spec.loader
            spec.loader.exec_module(mod)  # type: ignore
            plug = getattr(mod, "plugin", None)
            if isinstance(plug, Plugin):
                self.register(plug, user=user)
        except Exception:
            pass

    def reload_from_dir(self, path: str = "./data/plugins"):
        self.plugins = [
            p for p in self.plugins if p.name not in self._user_plugin_names
        ]
        self.job_handlers = {
            t: fn for t, fn in self.job_handlers.items() if t in {}
        }  # cleared
        self.event_handlers = [p.on_event for p in self.plugins if p.on_event]
        self._user_plugin_names.clear()
        self.load_from_dir(path)
