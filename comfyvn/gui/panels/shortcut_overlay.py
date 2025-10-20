# comfyvn/gui/panels/shortcut_overlay.py
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem
from comfyvn.core.shortcut_registry import shortcut_registry

class ShortcutOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("ShortcutOverlay")
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Registered Shortcuts"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Shortcut", "Handler", "Description"])
        v.addWidget(self.table)
        self.refresh()

    def refresh(self):
        items = shortcut_registry.all()
        self.table.setRowCount(len(items))
        for i, sc in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(sc.combo))
            self.table.setItem(i, 1, QTableWidgetItem(sc.handler))
            self.table.setItem(i, 2, QTableWidgetItem(sc.description))
