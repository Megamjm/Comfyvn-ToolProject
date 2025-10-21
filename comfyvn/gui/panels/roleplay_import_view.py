from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QSizePolicy, QTableWidget, QTableWidgetItem,
                               QTextEdit, QVBoxLayout, QWidget)

from comfyvn.core.notifier import notifier
from comfyvn.gui.services.server_bridge import ServerBridge


class RoleplayImportView(QWidget):
    """
    Studio dashboard for monitoring roleplay import jobs and inline logs.
    """

    jobs_loaded = Signal(dict)
    log_loaded = Signal(int, str)
    error_raised = Signal(str)
    refresh_complete = Signal()

    def __init__(
        self, server: Optional[ServerBridge] = None, base: Optional[str] = None
    ):
        super().__init__()
        self.setWindowTitle("Roleplay Import Jobs")
        self._server = server or ServerBridge(base)
        self._jobs: List[Dict[str, Any]] = []
        self._selected_job_id: Optional[int] = None

        self.jobs_loaded.connect(self._populate_table)
        self.log_loaded.connect(self._display_log)
        self.error_raised.connect(self._show_error)
        self.refresh_complete.connect(self._reset_state)

        self._build_ui()

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(10_000)
        self._auto_timer.timeout.connect(self.refresh_jobs)
        self._auto_timer.start()

        QTimer.singleShot(250, self.refresh_jobs)

    # ─────────────────────────────
    # UI construction
    # ─────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignTop)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Roleplay Import Jobs</b>"))
        header.addStretch(1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_jobs)
        header.addWidget(self.refresh_btn)

        self.log_btn = QPushButton("View Log")
        self.log_btn.clicked.connect(self.view_selected_log)
        self.log_btn.setEnabled(False)
        header.addWidget(self.log_btn)

        root.addLayout(header)

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("roleplayImportStatus")
        root.addWidget(self.status_label)

        self.table = QTableWidget(0, 7, self)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setHorizontalHeaderLabels(
            ["Job ID", "Status", "Title", "World", "Scene ID", "Asset UID", "Created"]
        )
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)
        header_view.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._handle_selection)
        root.addWidget(self.table)

        root.addWidget(QLabel("<b>Importer Log</b>"))
        self.log_view = QTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText(
            "Select a job and fetch the log to inspect importer output…"
        )
        self.log_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.log_view)

    # ─────────────────────────────
    # Job refresh & rendering
    # ─────────────────────────────
    def refresh_jobs(self) -> None:
        if not self.refresh_btn.isEnabled():
            return
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("Refreshing roleplay jobs…")

        def worker():
            result = self._server.get_json("/roleplay/imports", {"limit": 50})
            if not isinstance(result, dict):
                self.error_raised.emit("Invalid response from server.")
                self.refresh_complete.emit()
                return
            if not result.get("ok"):
                err = result.get("error") or f"HTTP {result.get('status')}"
                self.error_raised.emit(f"Importer refresh failed: {err}")
            self.jobs_loaded.emit(result)
            self.refresh_complete.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _populate_table(self, payload: Dict[str, Any]) -> None:
        data = payload.get("data") if isinstance(payload, dict) else None
        jobs = data.get("items", []) if isinstance(data, dict) else []
        self._jobs = jobs

        selected_id = self._selected_job_id

        self.table.setRowCount(len(jobs))
        for row_idx, job in enumerate(jobs):
            job_id = job.get("id")
            status = job.get("status") or "unknown"
            input_meta = job.get("input") or {}
            output_meta = job.get("output") or {}
            import_meta = self._load_import_meta(job)

            title = input_meta.get("title") or import_meta.get("title") or ""
            world = input_meta.get("world") or import_meta.get("world") or ""
            scene_id = output_meta.get("scene_id") or ""
            asset_uid = output_meta.get("asset_uid") or ""
            created = job.get("submit_ts") or ""

            cells = [
                str(job_id or ""),
                status,
                title,
                world,
                str(scene_id),
                str(asset_uid),
                created,
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(row_idx, col, item)

            if selected_id and job_id == selected_id:
                self.table.selectRow(row_idx)

        self.status_label.setText(f"Loaded {len(jobs)} roleplay import job(s).")
        self.log_btn.setEnabled(self.table.currentRow() >= 0)

    @staticmethod
    def _load_import_meta(job: Dict[str, Any]) -> Dict[str, Any]:
        record = job.get("import") or {}
        meta = record.get("meta")
        if isinstance(meta, dict):
            return meta
        if isinstance(meta, str):
            try:
                return json.loads(meta)
            except json.JSONDecodeError:
                return {}
        return {}

    # ─────────────────────────────
    # Log handling
    # ─────────────────────────────
    def _handle_selection(self) -> None:
        row = self.table.currentRow()
        has_selection = row >= 0
        self.log_btn.setEnabled(has_selection)
        if has_selection:
            job_id_text = self.table.item(row, 0).text()
            try:
                self._selected_job_id = int(job_id_text)
            except ValueError:
                self._selected_job_id = None
        else:
            self._selected_job_id = None

    def view_selected_log(self) -> None:
        if not self._selected_job_id:
            notifier.toast("warn", "Select a job to view its log.")
            return
        job_id = self._selected_job_id
        self.status_label.setText(f"Fetching log for job {job_id}…")

        def worker():
            result = self._server.get_json(
                f"/roleplay/imports/{job_id}/log", timeout=5.0
            )
            if not isinstance(result, dict):
                self.error_raised.emit("Invalid log response.")
                return
            if not result.get("ok"):
                err = result.get("error") or f"HTTP {result.get('status')}"
                self.error_raised.emit(f"Log fetch failed: {err}")
                return
            data = result.get("data")
            text = ""
            if isinstance(data, dict):
                text = json.dumps(data, indent=2, ensure_ascii=False)
            elif isinstance(data, str):
                text = data
            else:
                text = str(data)
            self.log_loaded.emit(job_id, text)

        threading.Thread(target=worker, daemon=True).start()

    def _display_log(self, job_id: int, text: str) -> None:
        self.status_label.setText(f"Log loaded for job {job_id}.")
        self.log_view.setPlainText(text)

    def _show_error(self, message: str) -> None:
        notifier.toast("error", message)
        self.status_label.setText(message)

    def _reset_state(self) -> None:
        self.refresh_btn.setEnabled(True)
