from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/shortcut_ext_bridge.py
from typing import Callable
from comfyvn.core.shortcut_registry import shortcut_registry

def register_extension_shortcuts(ext_id: str, items: dict[str,str], callbacks: dict[str, Callable] | None=None):
    """
    Extensions call this to declare default keybindings and optional handlers.
    Example:
      register_extension_shortcuts("my_ext", {"my_action": "Ctrl+Alt+M"}, {"my_action": on_my_action})
    """
    shortcut_registry.register_extension_shortcuts(ext_id, items, callbacks or {})