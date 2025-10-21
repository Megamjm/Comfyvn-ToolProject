from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

from PySide6.QtGui import QAction


# Menu shape: top-level name -> list of (label, callback, section)
# "section" lets providers group with separators without coupling
@dataclass
class MenuRegistry:
    items: Dict[str, List[Tuple[str, Callable, str]]] = field(default_factory=dict)

    def add(self, menu: str, label: str, callback: Callable, section: str = "default"):
        self.items.setdefault(menu, []).append((label, callback, section))

    def clear_menu(self, menu: str):
        self.items.pop(menu, None)

    def clear_all(self):
        self.items.clear()


# Global registry (imported by GUI + extensions)
menu_registry = MenuRegistry()
