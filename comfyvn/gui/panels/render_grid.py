from __future__ import annotations

import json

import requests
from PySide6.QtGui import QAction
# comfyvn/gui/panels/render_grid.py
from PySide6.QtWidgets import (QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)


class RenderGridPanel(QWidget):
    def __init__(self, base="http://127.0.0.1:8001", parent=None):
        super().__init__(parent)
        self.base = base
        self.setWindowTitle("Render Grid")
        self.layout = QVBoxLayout(self)
        self.btn_refresh = QPushButton("Refresh targets")
        self.btn_refresh.clicked.connect(self.refresh)
        self.layout.addWidget(self.btn_refresh)
        self.list = QListWidget()
        self.layout.addWidget(self.list)
        self.btn_test = QPushButton("Test selected")
        self.btn_test.clicked.connect(self.test_selected)
        self.layout.addWidget(self.btn_test)
        self.refresh()

    def refresh(self):
        try:
            r = requests.get(self.base + "/render/targets", timeout=5).json()
            self.list.clear()
            provs = r.get("providers", {})
            order = r.get("priority_order", [])
            for pid in order:
                p = provs.get(pid, {})
                item = QListWidgetItem(
                    f"{pid} [{p.get('service')}] {p.get('base','')}  active={p.get('active',True)}"
                )
                item.setData(32, pid)
                self.list.addItem(item)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def test_selected(self):
        item = self.list.currentItem()
        if not item:
            return
        pid = item.data(32)
        try:
            r = requests.get(self.base + f"/render/health/{pid}", timeout=5).json()
            QMessageBox.information(self, "Health", json.dumps(r, indent=2))
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
