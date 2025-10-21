# comfyvn/gui/panels/task_hub_panel.py
from __future__ import annotations

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from comfyvn.core.task_hub import task_hub


class TaskHubPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("TaskHubPanel")
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Async Task Hub"))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Label", "Status", "Progress"])
        v.addWidget(self.table)

        h = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_cancel = QPushButton("Cancel Selected")
        h.addWidget(self.btn_refresh)
        h.addWidget(self.btn_cancel)
        v.addLayout(h)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_cancel.clicked.connect(self.cancel_selected)
        self.refresh()

    def refresh(self):
        items = task_hub.all()
        self.table.setRowCount(len(items))
        for i, t in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(t.id))
            self.table.setItem(i, 1, QTableWidgetItem(t.label))
            self.table.setItem(i, 2, QTableWidgetItem(t.status))
            self.table.setItem(i, 3, QTableWidgetItem(f"{int(t.progress*100)}%"))

    def cancel_selected(self):
        i = self.table.currentRow()
        if i < 0:
            return
        tid = self.table.item(i, 0).text()
        task_hub.cancel(tid)
        self.refresh()
