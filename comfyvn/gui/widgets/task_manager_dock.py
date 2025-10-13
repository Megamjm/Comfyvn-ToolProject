# comfyvn/gui/widgets/task_manager_dock.py
# [🎨 GUI Code Production Chat]
# Phase 3.7 – Task Manager Dock (WebSocket + REST Sync)  # COMFYVN Architect

import json, asyncio
from pathlib import Path
from datetime import datetime

import requests
import websockets

from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QHBoxLayout,
    QPushButton,
    QHeaderView,
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread

from comfyvn.gui.components.task_console_window import TaskConsoleWindow


# ---------------------------------------------------------------------------
# Background WebSocket Thread
# ---------------------------------------------------------------------------
class _WebSocketWorker(QThread):
    message_received = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._running = True

    def run(self):
        asyncio.run(self._listen())

    async def _listen(self):
        try:
            async with websockets.connect(self.url) as ws:
                while self._running:
                    msg = await ws.recv()
                    self.message_received.emit(msg)
        except Exception as e:
            self.message_received.emit(f"[WebSocket error] {e}")

    def stop(self):
        self._running = False


# ---------------------------------------------------------------------------
# Task Manager Dock
# ---------------------------------------------------------------------------
class TaskManagerDock(QDockWidget):
    """Task Manager Dock – View, control, and archive backend jobs."""

    def __init__(self, server_url="http://127.0.0.1:8000", parent=None):
        super().__init__("Task Manager", parent)
        self.server_url = server_url.rstrip("/")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        # --- UI ---
        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Job ID", "Status", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        control_bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter jobs…")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_jobs)
        control_bar.addWidget(self.search)
        control_bar.addWidget(self.refresh_btn)
        layout.addLayout(control_bar)

        # --- Logs ---
        self.log_dir = Path("./logs/jobs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate_logs)
        self.timer.start(60000)

        # --- Local job shim store (for GUI-triggered tasks)
        self._local_jobs = {}  # {job_id: {"id","label","status"}}

        # --- WebSocket ---
        ws_url = f"ws://{self.server_url.split('://')[-1]}/ws/jobs"
        self.worker = _WebSocketWorker(ws_url)
        self.worker.message_received.connect(self.on_message)
        self.worker.start()

        self.refresh_jobs()

    # ---------------- Local job shims (used by SettingsUI) ----------------
    def add_job(self, job_id: str, label: str, status: str = "running"):
        self._local_jobs[job_id] = {"id": job_id, "label": label, "status": status}
        self.refresh_jobs()

    def update_job_status(self, job_id: str, status: str):
        if job_id in self._local_jobs:
            self._local_jobs[job_id]["status"] = status
        self.refresh_jobs()

    def _merge_jobs(self, server_jobs: list) -> list:
        merged = {}
        for j in server_jobs:
            jid = j.get("id") or j.get("job_id") or ""
            if not jid:
                continue
            merged[jid] = j
        for jid, rec in self._local_jobs.items():
            if jid not in merged:
                merged[jid] = {
                    "id": jid,
                    "status": rec.get("status", ""),
                    "label": rec.get("label", "local"),
                }
        return list(merged.values())

    # ---------------- Networking ----------------
    def _http_get(self, path: str) -> dict:
        try:
            r = requests.get(f"{self.server_url}{path}", timeout=10)
            return r.json()
        except Exception as e:
            self._log_event(f"[GET error] {e}")
            return {}

    # ---------------- Events ----------------
    def on_message(self, msg: str):
        self._log_event(msg)
        self.refresh_jobs()

    def refresh_jobs(self):
        try:
            res = self._http_get("/jobs/poll")
            server_jobs = res.get("jobs", []) if isinstance(res, dict) else []
            jobs = self._merge_jobs(server_jobs)

            self.table.setRowCount(0)
            needle = self.search.text().lower().strip()

            for job in jobs:
                jid = job.get("id") or job.get("job_id") or ""
                status = job.get("status", "")
                if needle and needle not in jid.lower():
                    continue

                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(jid))
                self.table.setItem(row, 1, QTableWidgetItem(status))

                label = job.get("label") or "Open Console"
                btn = QPushButton(label)
                btn.clicked.connect(lambda _, _jid=jid: self.open_console(_jid))
                self.table.setCellWidget(row, 2, btn)
        except Exception as e:
            self._log_event(f"[Poll error] {e}")

    def open_console(self, job_id):
        dlg = TaskConsoleWindow(self.server_url, job_id, self)
        dlg.show()

    # ---------------- Logs ----------------
    def _log_event(self, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = self.log_dir / f"{ts}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": ts, "event": msg}, f, indent=2)
        self._rotate_logs()

    def _rotate_logs(self):
        files = sorted(self.log_dir.glob("*.json"))
        if len(files) > 10:
            for f in files[:-10]:
                f.unlink()

    # ----------------------------------------------------------------------
    # Qt Lifecycle
    # ----------------------------------------------------------------------
    def closeEvent(self, e):
        try:
            if hasattr(self, "worker") and self.worker.isRunning():
                self.worker.stop()
                self.worker.wait(1500)
        finally:
            super().closeEvent(e)

    # ----------------------------------------------------------------------
    # Event Bridge Hooks (Safe no-ops if unused)
    # ----------------------------------------------------------------------
    def handle_event(self, event: dict):
        """Handle generic job events emitted by MainWindow."""
        etype = event.get("type")
        payload = event.get("payload", {})
        print(f"[TaskManagerDock] Received event: {etype} | {payload}")
        # Example integration: automatically add a local job
        jid = payload.get("id") or payload.get("job_id") or None
        if jid:
            self.add_job(
                jid,
                payload.get("label", "external event"),
                payload.get("status", "running"),
            )

    def handle_update(self, update: dict):
        """Handle task status updates from MainWindow."""
        job_id = update.get("id")
        status = update.get("status")
        details = update.get("details", {})
        print(f"[TaskManagerDock] Update: {job_id} → {status}")
        if job_id:
            self.update_job_status(job_id, status)
