from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

@dataclass
class Shortcut:
    id: str
    label: str
    handler: str  # MainWindow method name
    hotkey: Optional[str] = None

class ShortcutRegistry:
    def __init__(self):
        self._items: List[Shortcut] = []
    def add(self, sc: Shortcut):
        self._items.append(sc)
    def clear(self):
        self._items.clear()
    def iter_actions(self) -> Iterable[Shortcut]:
        return list(self._items)

shortcut_registry = ShortcutRegistry()

def load_shortcuts_from_folder(registry: ShortcutRegistry, folder: Path):
    registry.clear()
    if not folder.exists(): return
    for js in sorted(folder.rglob("*.json")):
        try:
            data = json.loads(js.read_text(encoding="utf-8"))
            if isinstance(data, dict): data = [data]
            for it in data:
                sc = Shortcut(
                    id=str(it.get("id") or it.get("label")),
                    label=str(it.get("label") or ""),
                    handler=str(it.get("handler") or ""),
                    hotkey=it.get("hotkey")
                )
                registry.add(sc)
        except Exception as e:
            print("[Shortcuts] Failed", js, ":", e)
