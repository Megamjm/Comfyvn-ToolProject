# comfyvn/gui/components/task_manager_dock.py
# 🎨 ComfyVN Task Manager Dock – v1.2-F+ (Stable)
# Live Job Stream + Polling Fallback + Log Export + Filters + Tray Notifications

import os, json, threading, asyncio, websockets
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLineEdit, QHBoxLayout, QPushButton, QMenu, QHeaderView, QMessageBox,
    QSplitter, QSystemTrayIcon
)
from PySide6.QtCore import Qt, QTimer, QPoint, QUrl, QThread, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QCursor

from comfyvn.gui.widgets.task_console_window import TaskConsoleWindow
from comfyvn.gui.server_bridge import ServerBridge
from comfyvn.gui.components.task_manager_controls import TaskManagerControls
from comfyvn.gui.components.job_filter_model import JobFilterModel
from comfyvn.gui.components.charts.resource_chart_widget import ResourceChartWidget


# ---------------------------------------------------------------------------
# Background WebSocket Worker
# ---------------------------------------------------------------------------
class _WebSocketWorker(QThread):
    message_received = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._stop = False

    def run(self):
        asyncio.run(self._loop())

    async def _loop(self):
        """Persistent WebSocket connection with auto-reconnect."""
        while not self._stop:
            try:
                async with websockets.connect(self.url, ping_interval=20) as ws:
                    async for msg in ws:
                        if self._stop:
                            break
                        self.message_received.emit(msg)
            except Exception as e:
                print(f"[TaskManagerDock] WebSocket error: {e}")
                await asyncio.sleep(3)

    def stop(self):
        self._stop = True


# ---------------------------------------------------------------------------
# Task Manager Dock
# ---------------------------------------------------------------------------
class TaskManagerDock(QDockWidget):
    """ComfyVN Task Manager – Live Job Stream, Filters, and Optimization Controls."""

    def __init__(self, server_url="http://127.0.0.1:8001", parent=None):
        super().__init__("Pending Tasks", parent)
        self.server_url = server_url.rstrip("/")
        self.bridge = ServerBridge(self.server_url)
        self.ws_url = self.server_url.replace("http", "ws") + "/ws/jobs"

        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.setMinimumWidth(520)

        # -------------------- Core UI --------------------
        container = QWidget()
        vlayout = QVBoxLayout(container)
        vlayout.setContentsMargins(5, 5, 5, 5)
        vlayout.setSpacing(6)
        self.setWidget(container)

        # Controls bar
        self.controls = TaskManagerControls(self.server_url, self)
        self.controls.message.connect(self._notify)
        self.controls.refresh_jobs.connect(self._poll_fallback)
        vlayout.addWidget(self.controls)

        # Filter + export bar
        filter_bar = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter jobs (type/status)…")
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.btn_export_logs = QPushButton("💾 Export All Logs")
        self.btn_export_logs.clicked.connect(self._export_all_logs)
        filter_bar.addWidget(self.filter_edit)
        filter_bar.addWidget(self.btn_export_logs)
        vlayout.addLayout(filter_bar)

        # Job table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Type", "Status", "Progress"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_menu)
        self.table.cellDoubleClicked.connect(self._open_console)
        vlayout.addWidget(self.table)

        # Resource chart
        self.chart = ResourceChartWidget(self)
        vlayout.addWidget(self.chart)

        # System tray notifications
        self.tray = QSystemTrayIcon(QIcon.fromTheme("dialog-information"), parent)
        if not self.tray.icon().isNull():
            self.tray.setToolTip("ComfyVN Task Manager")
        else:
            self.tray.setIcon(QIcon())  # fallback icon
        self.tray.setVisible(True)

        # Internal state
        self._latest_jobs = []
        self.log_dir = Path("./logs/jobs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_logs = 10
        self._notified_jobs = {}

        # -------------------- Networking --------------------
        self.timer = QTimer()
        self.timer.timeout.connect(self._poll_fallback)
        self.timer.start(10000)  # every 10 seconds

        self.ws_thread = _WebSocketWorker(self.ws_url)
        self.ws_thread.message_received.connect(self._handle_ws_message)
        self.ws_thread.start()

        # Job filter model
        self.filter_model = JobFilterModel(self)
        self.controls.chk_cpu.stateChanged.connect(self._update_filters)
        self.controls.chk_gpu.stateChanged.connect(self._update_filters)
        self.controls.chk_active.stateChanged.connect(self._update_filters)
        self.controls.chk_failed.stateChanged.connect(self._update_filters)

    # ===============================================================
    # WebSocket Handling
    # ===============================================================
    def _handle_ws_message(self, message: str):
        try:
            data = json.loads(message)
        except Exception:
            return

        evt_type = data.get("type", "")
        if evt_type == "hello":
            jobs = data.get("jobs", [])
        else:
            job = data.get("job")
            if not job:
                return
            found = False
            for i, j in enumerate(self._latest_jobs):
                if j.get("id") == job.get("id"):
                    self._latest_jobs[i] = job
                    found = True
                    break
            if not found:
                self._latest_jobs.append(job)
            jobs = self._latest_jobs

        self._update_table(jobs)
        self._save_log(jobs)
        self._check_notifications(jobs)

    # ===============================================================
    # Polling Fallback
    # ===============================================================
    def _poll_fallback(self):
        """Fallback job polling using ServerBridge."""
        def _cb(data):
            jobs = data.get("jobs", [])
            self._latest_jobs = jobs
            self._update_table(jobs)
            self._save_log(jobs)
        try:
            self.bridge.get('/jobs/poll')
        except Exception as e:
            print(f"[TaskManagerDock] Poll error: {e}")

    # ===============================================================
    # Table + Filters
    # ===============================================================
    def _update_table(self, jobs):
        self.table.setRowCount(len(jobs))
        for row, j in enumerate(jobs):
            job_id = str(j.get("id", ""))
            job_type = j.get("type", "")
            job_status = j.get("status", "")
            progress = str(j.get("progress", ""))

            id_item = QTableWidgetItem(job_id)
            type_item = QTableWidgetItem(job_type)
            status_item = QTableWidgetItem(job_status)
            prog_item = QTableWidgetItem(progress)

            s = job_status.lower()
            color = {
                "queued": Qt.lightGray,
                "pending": Qt.lightGray,
                "processing": Qt.yellow,
                "running": Qt.yellow,
                "active": Qt.yellow,
                "complete": Qt.green,
                "done": Qt.green,
                "success": Qt.green,
                "error": Qt.red,
                "failed": Qt.red,
                "cancelled": Qt.gray,
                "stopped": Qt.gray
            }.get(s, Qt.white)
            status_item.setBackground(color)

            self.table.setItem(row, 0, id_item)
            self.table.setItem(row, 1, type_item)
            self.table.setItem(row, 2, status_item)
            self.table.setItem(row, 3, prog_item)

    def _update_filters(self):
        self.filter_model.set_filters(self.controls.collect_filters())
        self._apply_filter()

    def _apply_filter(self):
        """Apply text and checkbox filters simultaneously."""
        text = self.filter_edit.text().lower().strip()
        filters = self.controls.collect_filters()
        for i in range(self.table.rowCount()):
            job_type = self.table.item(i, 1).text().lower() if self.table.item(i, 1) else ""
            job_status = self.table.item(i, 2).text().lower() if self.table.item(i, 2) else ""

            visible = True
            if text and text not in (job_type + job_status):
                visible = False
            if filters["cpu_only"] and "cpu" not in job_type:
                visible = False
            if filters["gpu_only"] and "gpu" not in job_type:
                visible = False
            if filters["active"] and job_status not in ("running", "active", "processing"):
                visible = False
            if filters["failed"] and job_status not in ("failed", "error"):
                visible = False

            self.table.setRowHidden(i, not visible)

    # ===============================================================
    # Context Menu & Actions
    # ===============================================================
    def _show_menu(self, pos: QPoint):
        menu = QMenu(self)
        rows = list({i.row() for i in self.table.selectedIndexes()})
        ids = [self.table.item(r, 0).text() for r in rows if self.table.item(r, 0)]
        if ids:
            menu.addAction("🛑 Cancel", lambda: self._cancel_jobs(ids))
            menu.addSeparator()
            menu.addAction("💾 Export Selected Logs", lambda: self._export_selected_logs(ids))
            menu.addSeparator()
        menu.addAction("📂 Open Log Folder", self._open_log_folder)
        menu.addAction("🧹 Clear Logs", self._clear_logs)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _cancel_jobs(self, job_ids):
        for jid in job_ids:
            try:
                self.bridge.cancel_job(jid, lambda r: None)
            except Exception as e:
                print(f"[TaskManagerDock] Cancel job error: {e}")

    def _open_console(self, row):
        jid = self.table.item(row, 0).text()
        TaskConsoleWindow(self.server_url, jid, self)

    # ===============================================================
    # Notifications
    # ===============================================================
    def _check_notifications(self, jobs):
        for j in jobs:
            jid = j.get("id")
            status = j.get("status", "").lower()
            if jid not in self._notified_jobs:
                self._notified_jobs[jid] = status
            else:
                old = self._notified_jobs[jid]
                if old != status:
                    self._notified_jobs[jid] = status
                    if status in ("complete", "done", "success"):
                        self._notify(f"✅ Job Completed: {jid}")
                    elif status in ("error", "failed"):
                        self._notify(f"❌ Job Failed: {jid}")
                    elif status in ("cancelled",):
                        self._notify(f"⚠️ Job Cancelled: {jid}")

    def _notify(self, msg):
        try:
            self.tray.showMessage("ComfyVN Task Manager", msg, QSystemTrayIcon.Information, 4000)
        except Exception as e:
            print(f"[TaskManagerDock] Tray notify error: {e}")

    # ===============================================================
    # Logging & Export
    # ===============================================================
    def _save_log(self, jobs):
        if not jobs:
            return
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        f = self.log_dir / f"jobs_{ts}.json"
        try:
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(jobs, fp, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[TaskManagerDock] Log write error: {e}")
            return
        self._rotate_logs()

    def _rotate_logs(self):
        files = sorted(self.log_dir.glob("jobs_*.json"), key=os.path.getmtime)
        if len(files) > self.max_logs:
            for f in files[:-self.max_logs]:
                try:
                    f.unlink()
                except Exception:
                    pass

    def _open_log_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_dir.resolve())))

    def _clear_logs(self):
        for f in self.log_dir.glob("jobs_*.json"):
            try:
                f.unlink()
            except Exception:
                pass
        QMessageBox.information(self, "Logs Cleared", "All logs deleted.")

    def _export_all_logs(self):
        out = self.log_dir / "jobs_merged.json"
        logs = []
        for f in sorted(self.log_dir.glob("jobs_*.json")):
            try:
                logs.extend(json.load(open(f, "r", encoding="utf-8")))
            except Exception:
                pass
        with open(out, "w", encoding="utf-8") as fp:
            json.dump(logs, fp, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "Export Complete", f"Merged logs → {out}")

    def _export_selected_logs(self, job_ids):
        out = self.log_dir / "jobs_selected.json"
        sel = [j for j in self._latest_jobs if j.get("id") in job_ids]
        with open(out, "w", encoding="utf-8") as fp:
            json.dump(sel, fp, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "Export Complete", f"Selected logs → {out}")

    # ===============================================================
    # Cleanup
    # ===============================================================
    def closeEvent(self, event):
        """Stop background threads when dock is closed."""
        try:
            self.ws_thread.stop()
        except Exception:
            pass
        super().closeEvent(event)
