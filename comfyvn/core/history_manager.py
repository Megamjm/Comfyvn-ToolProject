from PySide6.QtGui import QAction
# comfyvn/core/history_manager.py
# [COMFYVN Architect | v1.4 | this chat]
from typing import Callable, Optional, List, Dict
from comfyvn.core.event_bus import subscribe

class HistoryAction:
    def __init__(self, do_fn: Callable[[], None], undo_fn: Callable[[], None], desc: str = ""):
        self.do_fn = do_fn
        self.undo_fn = undo_fn
        self.desc = desc

class HistoryManager:
    def __init__(self, max_depth: int = 500):
        self.stack: List[HistoryAction] = []
        self.redo_stack: List[HistoryAction] = []
        self.max_depth = max_depth

    def push(self, action: HistoryAction, execute: bool = True):
        # trim if needed
        if len(self.stack) >= self.max_depth:
            self.stack.pop(0)
        self.stack.append(action)
        self.redo_stack.clear()
        if execute:
            action.do_fn()

    def undo(self):
        if not self.stack: return
        action = self.stack.pop()
        try:
            action.undo_fn()
        finally:
            self.redo_stack.append(action)

    def redo(self):
        if not self.redo_stack: return
        action = self.redo_stack.pop()
        try:
            action.do_fn()
        finally:
            self.stack.append(action)

history = HistoryManager()

# bind to global bus signals so GUI triggers can be decoupled
subscribe("action.undo", lambda _=None: history.undo())
subscribe("action.redo", lambda _=None: history.redo())