from __future__ import annotations
import importlib.util, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
from PySide6.QtGui import QAction

@dataclass
class MenuItem:
    label: str
    handler: str
    section: str = "View"
    separator_before: bool = False

class MenuRegistry:
    def __init__(self):
        self.items: List[MenuItem] = []
    def add(self, label: str, handler: str, section: str="View", separator_before: bool=False):
        self.items.append(MenuItem(label, handler, section, separator_before))
    def by_section(self) -> Dict[str, List[MenuItem]]:
        out: Dict[str, List[MenuItem]] = {}
        for it in self.items:
            out.setdefault(it.section, []).append(it)
        return out
    def clear(self):
        self.items.clear()

menu_registry = MenuRegistry()

def _load_py_module(mod_path: Path):
    spec = importlib.util.spec_from_file_location(mod_path.stem, mod_path)
    if not spec or not spec.loader: return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_path.stem] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod

def reload_from_extensions(registry: MenuRegistry, base_folder: Path = Path("extensions")):
    """Load python files under base_folder that define `register(menu_registry)`."""
    registry.clear()
    if not base_folder.exists():
        return
    for py in sorted(base_folder.rglob("*.py")):
        try:
            mod = _load_py_module(py)
            if not mod: continue
            fn = getattr(mod, "register", None)
            if callable(fn):
                fn(registry)
        except Exception as e:
            print("[Extensions] Failed to load", py, ":", e)
