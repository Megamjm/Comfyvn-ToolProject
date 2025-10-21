from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
# comfyvn/gui/panels/task_manager_dock.py
# [COMFYVN Architect | v1.3 | this chat]
from PySide6.QtWidgets import (QHeaderView, QProgressBar, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from comfyvn.core.event_bus import subscribe, unsubscribe


class TaskManagerDock(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tasks")
        self.rows = {}  # id -> row
        v = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Status", "Progress"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table)
        subscribe("task.enqueued", self._on_enq)
        subscribe("task.started", self._on_start)
        subscribe("task.progress", self._on_prog)
        subscribe("task.finished", self._on_done)
        subscribe("task.error", self._on_err)

    def closeEvent(self, e):
        unsubscribe("task.enqueued", self._on_enq)
        unsubscribe("task.started", self._on_start)
        unsubscribe("task.progress", self._on_prog)
        unsubscribe("task.finished", self._on_done)
        unsubscribe("task.error", self._on_err)
        super().closeEvent(e)

    def _ensure_row(self, tid, name):
        if tid in self.rows:
            return self.rows[tid]
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(tid))
        self.table.setItem(r, 1, QTableWidgetItem(name))
        self.table.setItem(r, 2, QTableWidgetItem("queued"))
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        self.table.setCellWidget(r, 3, bar)
        self.rows[tid] = r
        return r

    def _update_status(self, tid, status):
        r = self.rows.get(tid)
        if r is None:
            return
        self.table.setItem(r, 2, QTableWidgetItem(status))

    def _update_prog(self, tid, pct):
        r = self.rows.get(tid)
        if r is None:
            return
        w = self.table.cellWidget(r, 3)
        if isinstance(w, QProgressBar):
            w.setValue(int(pct))

    def _on_enq(self, d):
        self._ensure_row(d["id"], d["name"])

    def _on_start(self, d):
        self._update_status(d["id"], "running")

    def _on_prog(self, d):
        self._update_prog(d["id"], d["progress"])

    def _on_done(self, d):
        self._update_status(d["id"], "done")
        self._update_prog(d["id"], 100)

    def _on_err(self, d):
        self._update_status(d["id"], "error")
