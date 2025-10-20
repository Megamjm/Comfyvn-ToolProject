from PySide6.QtGui import QAction
# comfyvn/gui/panels/history_view.py
# [COMFYVN Architect | v1.5 | this chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt
from comfyvn.core.history_manager import history
from comfyvn.core.event_bus import subscribe

class HistoryView(QWidget):
    """Visual stack viewer for HistoryManager."""
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Undo / Redo Stack"))
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        hb = QHBoxLayout()
        self.btn_undo = QPushButton("Undo"); self.btn_redo = QPushButton("Redo")
        hb.addWidget(self.btn_undo); hb.addWidget(self.btn_redo)
        v.addLayout(hb)

        self.btn_undo.clicked.connect(lambda: (history.undo(), self.refresh()))
        self.btn_redo.clicked.connect(lambda: (history.redo(), self.refresh()))
        self.refresh()

        subscribe("action.undo", lambda _: self.refresh())
        subscribe("action.redo", lambda _: self.refresh())

    def refresh(self):
        self.list.clear()
        for act in reversed(history.stack[-50:]):
            self.list.addItem(f"✓ {act.desc or 'Unnamed action'}")
        for act in history.redo_stack[:50]:
            self.list.addItem(f"↩ {act.desc or 'Redo available'}")