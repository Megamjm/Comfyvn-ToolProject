from __future__ import annotations
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel
from PySide6.QtCore import QTimer
import requests

class JobsPanel(QWidget):
    def __init__(self, base: str = "http://127.0.0.1:8001"):
        super().__init__()
        self.base = base.rstrip("/")
        self.lbl = QLabel("Active Jobs")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Kind", "Status", "Timestamp"])

        lay = QVBoxLayout(self)
        lay.addWidget(self.lbl)
        lay.addWidget(self.table)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def _get(self, path: str):
        try:
            r = requests.get(self.base + path, timeout=2)
            if r.status_code < 400:
                return r.json()
        except Exception:
            return None

    def refresh(self):
        data = self._get("/jobs/all") or {}
        jobs = data.get("jobs") or []
        self.table.setRowCount(len(jobs))
        for row, j in enumerate(jobs):
            self.table.setItem(row, 0, QTableWidgetItem(j.get("id","")))
            self.table.setItem(row, 1, QTableWidgetItem(j.get("kind","")))
            self.table.setItem(row, 2, QTableWidgetItem(j.get("status","")))
            self.table.setItem(row, 3, QTableWidgetItem(j.get("ts","")))