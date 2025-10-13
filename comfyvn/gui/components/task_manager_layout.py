# comfyvn/gui/components/task_manager_layout.py
# 🧩 Unified Task Manager Layout — v1.0 (Phase 3.5-L)
# Combines TaskManagerDock (left) + JobDetailPanel (right) + Resource Bar (bottom)
# [🎨 GUI Code Production Chat]

import threading, requests
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QLabel, QSizePolicy

from comfyvn.gui.components.task_manager_dock import TaskManagerDock
from comfyvn.gui.components.job_detail_panel import JobDetailPanel
from comfyvn.gui.components.task_resource_bar import TaskResourceBar


class TaskManagerLayout(QWidget):
    """
    Drop-in composite view:
      • Left: TaskManagerDock (jobs table, ws sync, controls, chart)
      • Right: JobDetailPanel (selected job JSON + live logs + actions)
      • Bottom: TaskResourceBar (CPU/GPU/RAM)
    """

    def __init__(self, server_url="http://127.0.0.1:8001", parent=None):
        super().__init__(parent)
        self.server_url = server_url.rstrip("/")

        # ----- root layout -----
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ----- splitter with dock (left) + detail (right) -----
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)

        # Left: existing TaskManagerDock
        self.dock = TaskManagerDock(server_url=self.server_url, parent=self)
        self.splitter.addWidget(self.dock)

        # Right: Job detail inspector
        self.detail = JobDetailPanel(server_url=self.server_url, parent=self)
        self.splitter.addWidget(self.detail)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)

        # Bottom: compact resource bar
        self.resource_bar = TaskResourceBar(self)
        self.resource_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Header (optional status summary)
        self.status_lbl = QLabel("Task Manager Ready")
        self.status_lbl.setStyleSheet("color:#6aa84f; font-weight:bold;")

        # Assemble
        root.addWidget(self.status_lbl)
        root.addWidget(self.splitter, 1)
        root.addWidget(self.resource_bar)

        # ----- wiring -----
        self._connect_signals()

    # ---------------------------------------------------------
    # Signal / Selection wiring
    # ---------------------------------------------------------
    def _connect_signals(self):
        # Row activation → load detail
        self.dock.table.itemSelectionChanged.connect(self._on_row_selected)
        self.dock.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        # Detail -> surface messages in status label
        self.detail.message.connect(self._set_status)

        # When TaskManagerDock refreshes from WS/REST it re-renders the table;
        # keep selection stable if possible:
        # (No explicit signal exposed, so rely on selection change triggers.)

    def _on_row_selected(self):
        row = self._current_row()
        if row is None:
            return
        jid = self._job_id_at(row)
        if not jid:
            return
        self._fetch_and_bind_job(jid)

    def _on_cell_double_clicked(self, row: int, _col: int):
        jid = self._job_id_at(row)
        if jid:
            self._fetch_and_bind_job(jid)

    def _current_row(self):
        sel = self.dock.table.selectionModel()
        if not sel or not sel.hasSelection():
            return None
        return sel.selectedRows()[0].row()

    def _job_id_at(self, row: int) -> str:
        it = self.dock.table.item(row, 0)
        return it.text() if it else ""

    # ---------------------------------------------------------
    # Networking helpers
    # ---------------------------------------------------------
    def _fetch_and_bind_job(self, job_id: str):
        self._set_status(f"Loading job {job_id} …")

        def _work():
            try:
                r = requests.get(f"{self.server_url}/jobs/{job_id}", timeout=6)
                if r.status_code == 200:
                    js = r.json()
                    job = js.get("job") or {"id": job_id}
                else:
                    job = {"id": job_id, "status": f"HTTP {r.status_code}"}
            except Exception as e:
                job = {"id": job_id, "status": f"error: {e}"}
            self.detail.set_job(job)
            self._set_status(f"Selected job: {job_id}")

        threading.Thread(target=_work, daemon=True).start()

    # ---------------------------------------------------------
    # Status helper
    # ---------------------------------------------------------
    def _set_status(self, text: str):
        self.status_lbl.setText(text)
        # simple color hinting
        low = text.lower()
        if any(k in low for k in ("error", "fail")):
            self.status_lbl.setStyleSheet("color:#cc0000; font-weight:bold;")
        elif any(
            k in low for k in ("loading", "refresh", "optimiz", "move", "rebalance")
        ):
            self.status_lbl.setStyleSheet("color:#e69138; font-weight:bold;")
        else:
            self.status_lbl.setStyleSheet("color:#6aa84f; font-weight:bold;")
