import importlib.util
import sys
import types
# comfyvn/server/core/plugins.py
from pathlib import Path
from typing import Any, Callable, Dict, List

from PySide6.QtGui import QAction

HOOKS = [
    "on_scene_build",
    "on_render_start",
    "on_character_load",
    "on_asset_registered",
]


class PluginHost:
    def __init__(self, root="plugins"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.plugins: List[types.ModuleType] = []
        self.reload()

    def reload(self):
        self.plugins.clear()
        for py in self.root.glob("*.py"):
            mod = self._load(py)
            if mod:
                self.plugins.append(mod)

    def _load(self, path: Path):
        try:
            spec = importlib.util.spec_from_file_location(path.stem, str(path))
            m = importlib.util.module_from_spec(spec)  # type: ignore
            assert spec and spec.loader
            sys.modules[path.stem] = m
            spec.loader.exec_module(m)  # type: ignore
            return m
        except Exception:
            return None

    def call(self, hook: str, *args, **kwargs):
        for m in self.plugins:
            fn = getattr(m, hook, None)
            if callable(fn):
                try:
                    fn(*args, **kwargs)
                except Exception:
                    pass
