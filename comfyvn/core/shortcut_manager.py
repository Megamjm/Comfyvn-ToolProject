# comfyvn/core/shortcut_manager.py
# [COMFYVN Architect | v1.2 | corrected import]
from typing import Callable, Dict
from PySide6.QtGui import QAction, QKeySequence

class ShortcutManager:
    """Central registry for application and panel shortcuts."""
    _actions: Dict[str, Dict] = {}

    @classmethod
    def register(cls, parent, name: str, sequence: str, callback: Callable, tip: str = ""):
        act = QAction(name, parent)
        if sequence:
            act.setShortcut(QKeySequence(sequence))
        if tip:
            act.setToolTip(tip)
        act.triggered.connect(callback)
        parent.addAction(act)
        cls._actions[name] = {"sequence": sequence, "callback": callback, "action": act}
        return act

    @classmethod
    def list_shortcuts(cls) -> Dict[str, str]:
        return {k: v["sequence"] or "" for k, v in cls._actions.items()}

    @classmethod
    def rebind(cls, name: str, new_seq: str):
        if name in cls._actions:
            act = cls._actions[name]["action"]
            act.setShortcut(QKeySequence(new_seq))
            cls._actions[name]["sequence"] = new_seq

# Global shared instance for extension access
shortcut_manager = ShortcutManager