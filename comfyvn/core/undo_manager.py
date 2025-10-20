from PySide6.QtGui import QAction
# comfyvn/core/undo_manager.py
# [COMFYVN Architect | v1.2 | this chat]
class UndoManager:
    def __init__(self):
        self.stack = []        # [(do, undo, desc)]
        self.redo_stack = []

    def push(self, do_fn, undo_fn, desc=""):
        self.stack.append((do_fn, undo_fn, desc))
        self.redo_stack.clear()
        do_fn()

    def undo(self):
        if not self.stack: return
        do_fn, undo_fn, desc = self.stack.pop()
        try: undo_fn()
        finally: self.redo_stack.append((do_fn, undo_fn, desc))

    def redo(self):
        if not self.redo_stack: return
        do_fn, undo_fn, desc = self.redo_stack.pop()
        try: do_fn()
        finally: self.stack.append((do_fn, undo_fn, desc))

undo_manager = UndoManager()