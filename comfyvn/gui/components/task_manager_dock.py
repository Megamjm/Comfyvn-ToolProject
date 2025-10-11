# comfyvn/gui/components/task_manager_dock.py
# [🎨 GUI Code Production Chat]
# Phase 3.7 – Full Task Management System (Notifications + Log Export + Filters)

import os, json, threading, requests
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLineEdit, QHBoxLayout, QPushButton, QMenu, QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QPoint, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QAction, QCursor, QSystemTrayIcon
from comfyvn.gui.components.task_console_window import TaskConsoleWindow


class TaskManagerDock(QDockWidget):
    """ComfyVN Task Manager – View, Control, and Archive Backend Jobs."""

    def __init__(self, server_url="http://127.0.0.1:8000", parent=None):
        super().__init__("Pending Tasks", parent)
        self.server_url = server_url.rstrip("/")
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.setMinimumWidth(450)

        # 📊 Layout Setup
        container = QWidget()
        vlayout = QVBoxLayout(container)
        vlayout.setContentsMargins(5, 5, 5, 5)
        self.setWidget(container)

        # 🔍 Filter bar
        filter_bar = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter jobs (type/status)...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.btn_export_logs = QPushButton("Export All Logs")
        self.btn_export_logs.clicked.connect(self._export_all_logs)
        filter_bar.addWidget(self.filter_edit)
        filter_bar.addWidget(self.btn_export_logs)
        vlayout.addLayout(filter_bar)

        # 🧾 Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Type", "Status", "Progress"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_menu)
        self.table.cellDoubleClicked.connect(self._open_console)
        vlayout.addWidget(self.table)

        # 🔔 Notification tray
        self.tray = QSystemTrayIcon(QIcon.fromTheme("dialog-information"), parent)
        self.tray.setVisible(True)

        # 🔄 Refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)

        # 🧩 Cache and paths
        self._latest_jobs = []
        self.log_dir = Path("./logs/jobs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_logs = 10
        self._notified_jobs = {}

    # ===============================================================
    # Networking
    # ===============================================================
    def refresh(self):
        """Fetch live jobs and update table."""
        def _work():
            try:
                r = requests.get(f"{self.server_url}/jobs/poll", timeout=15)
                data = r.json()
                jobs = data.get("jobs", [])
                self._latest_jobs = jobs
                self._update_table(jobs)
                self._save_log(jobs)
                self._check_notifications(jobs)
            except Exception:
                self._update_table([])
        threading.Thread(target=_work, daemon=True).start()

    # ===============================================================
    # Table UI
    # ===============================================================
    def _update_table(self, jobs):
        self.table.setRowCount(len(jobs))
        for row, j in enumerate(jobs):
            job_id = str(j.get("id"))
            job_type = j.get("type", "")
            job_status = j.get("status", "")
            progress = str(j.get("progress", ""))

            id_item = QTableWidgetItem(job_id)
            type_item = QTableWidgetItem(job_type)
            status_item = QTableWidgetItem(job_status)
            prog_item = QTableWidgetItem(progress)

            # 🎨 Color highlight
            status_lower = job_status.lower()
            if status_lower in ("running", "active"):
                status_item.setBackground(Qt.yellow)
            elif status_lower in ("done", "completed", "success"):
                status_item.setBackground(Qt.green)
            elif status_lower in ("failed", "error"):
                status_item.setBackground(Qt.red)
            else:
                status_item.setBackground(Qt.lightGray)

            self.table.setItem(row, 0, id_item)
            self.table.setItem(row, 1, type_item)
            self.table.setItem(row, 2, status_item)
            self.table.setItem(row, 3, prog_item)

    def _apply_filter(self):
        """Hide rows not matching filter text."""
        text = self.filter_edit.text().lower().strip()
        for i in range(self.table.rowCount()):
            match = any(
                text in (self.table.item(i, c).text().lower() if self.table.item(i, c) else "")
                for c in range(self.table.columnCount())
            )
            self.table.setRowHidden(i, not match if text else False)

    # ===============================================================
    # Context Menu
    # ===============================================================
    def _show_menu(self, pos: QPoint):
        menu = QMenu(self)
        selected_rows = list({i.row() for i in self.table.selectedIndexes()})
        job_ids = [self.table.item(r, 0).text() for r in selected_rows if self.table.item(r, 0)]

        if job_ids:
            menu.addAction("🛑 Kill Selected", lambda: self._batch_manage("kill", job_ids))
            menu.addAction("♻️ Reset Selected", lambda: self._batch_manage("reset", job_ids))
            menu.addSeparator()
            menu.addAction("⬆️ Move Up", lambda: self._batch_manage("move_up", job_ids))
            menu.addAction("⬇️ Move Down", lambda: self._batch_manage("move_down", job_ids))
            menu.addSeparator()
            menu.addAction("💾 Export Selected Logs", lambda: self._export_selected_logs(job_ids))
            menu.addSeparator()
        menu.addAction("📂 Open Log Folder", self._open_log_folder)
        menu.addAction("🧹 Clear All Logs", self._clear_logs)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ===============================================================
    # Job Management
    # ===============================================================
    def _batch_manage(self, action, job_ids):
        def _worker():
            for job_id in job_ids:
                try:
                    requests.post(f"{self.server_url}/jobs/manage",
                                  json={"id": job_id, "action": action}, timeout=10)
                except Exception:
                    pass
            self.refresh()
        threading.Thread(target=_worker, daemon=True).start()

    def _open_console(self, row):
        """Open log console for selected job."""
        job_id = self.table.item(row, 0).text()
        TaskConsoleWindow(self.server_url, job_id, self)

    # ===============================================================
    # Notification System
    # ===============================================================
    def _check_notifications(self, jobs):
        """Show desktop notifications for finished or failed jobs."""
        for j in jobs:
            jid = j.get("id")
            status = j.get("status", "").lower()
            if jid not in self._notified_jobs:
                self._notified_jobs[jid] = status
            else:
                old = self._notified_jobs[jid]
                if old != status:
                    self._notified_jobs[jid] = status
                    if status in ("done", "completed", "success"):
                        self._notify(f"✅ Job Completed: {jid}")
                    elif status in ("failed", "error"):
                        self._notify(f"❌ Job Failed: {jid}")

    def _notify(self, message: str):
        """Display a desktop notification."""
        self.tray.showMessage("ComfyVN Task Manager", message, QSystemTrayIcon.Information, 5000)

    # ===============================================================
    # Job Logging & History
    # ===============================================================
    def _save_log(self, jobs):
        if not jobs:
            return
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = self.log_dir / f"jobs_{ts}.json"
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(jobs, f, indent=2, ensure_ascii=False)
        except Exception:
            return
        self._rotate_logs()

    def _rotate_logs(self):
        files = sorted(self.log_dir.glob("jobs_*.json"))
        if len(files) > self.max_logs:
            for f in files[:-self.max_logs]:
                try:
                    f.unlink()
                except Exception:
                    pass

    def _open_log_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_dir.resolve())))

    def _clear_logs(self):
        count = 0
        for f in self.log_dir.glob("jobs_*.json"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        QMessageBox.information(self, "Logs Cleared", f"Deleted {count} file(s).")

    def _export_all_logs(self):
        """Export all logs into a single merged JSON file."""
        export_path = self.log_dir / "jobs_merged.json"
        logs = []
        for f in sorted(self.log_dir.glob("jobs_*.json")):
            try:
                logs.extend(json.load(open(f, "r", encoding="utf-8")))
            except Exception:
                pass
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "Export Complete", f"Merged logs saved:\n{export_path}")

    def _export_selected_logs(self, job_ids):
        """Write minimal history for selected jobs."""
        export_path = self.log_dir / "jobs_selected.json"
        selected = [j for j in self._latest_jobs if j.get("id") in job_ids]
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(selected, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "Export Complete", f"Selected logs saved:\n{export_path}")
# ===============================================================