# comfyvn/gui/components/job_detail_panel.py
# 🔎 Job Detail Panel — v1.0 (Phase 3.4-F)
# Per-job inspector: metadata, live logs, actions (Restart / Clone / Delete)
# [🎨 GUI Code Production Chat]

import json
import threading
import requests
from datetime import datetime

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QTextCursor, QAction, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QFormLayout,
    QToolBar,
    QMenu,
    QFileDialog,
    QMessageBox,
)

from comfyvn.gui.server_bridge import ServerBridge


class JobDetailPanel(QWidget):
    """
    Collapsible side panel for inspecting a single job:
      • Shows live-updating status and JSON metadata
      • Streams logs from /jobs/{id}/stream (if available) with fallback polling
      • Actions: Restart, Clone, Delete, Cancel
      • Utilities: Copy JSON, Save JSON, Save Logs
    """

    message = Signal(str)  # emits status messages for host to surface
    job_updated = Signal(dict)  # emits latest job payload on refresh

    def __init__(self, server_url="http://127.0.0.1:8001", parent=None):
        super().__init__(parent)
        self.server_url = server_url.rstrip("/")
        self.bridge = ServerBridge(self.server_url)
        self.current_job: dict = {}
        self.current_job_id: str | None = None
        self._stream_thread = None
        self._stream_stop = threading.Event()

        self._build_ui()

        # passive refresh (metadata) as fallback if no stream endpoint
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3000)
        self._poll_timer.timeout.connect(self._poll_job_meta)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Header: Job ID + status
        hdr = QHBoxLayout()
        self.lbl_title = QLabel("Job: —")
        self.lbl_title.setStyleSheet("font-weight: bold;")
        hdr.addWidget(self.lbl_title)
        hdr.addStretch(1)

        self.lbl_status = QLabel("Status: —")
        self.lbl_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hdr.addWidget(self.lbl_status)
        root.addLayout(hdr)

        # Toolbar
        self.toolbar = QToolBar(self)
        self.toolbar.setIconSize(self.toolbar.iconSize())  # default
        act_restart = QAction(QIcon.fromTheme("media-playlist-repeat"), "Restart", self)
        act_clone = QAction(QIcon.fromTheme("edit-copy"), "Clone", self)
        act_delete = QAction(QIcon.fromTheme("edit-delete"), "Delete", self)
        act_cancel = QAction(QIcon.fromTheme("process-stop"), "Cancel", self)
        act_copy_json = QAction(QIcon.fromTheme("edit-copy"), "Copy JSON", self)
        act_save_json = QAction(QIcon.fromTheme("document-save"), "Save JSON", self)
        act_save_log = QAction(QIcon.fromTheme("document-save"), "Save Logs", self)

        self.toolbar.addAction(act_restart)
        self.toolbar.addAction(act_clone)
        self.toolbar.addAction(act_cancel)
        self.toolbar.addAction(act_delete)
        self.toolbar.addSeparator()
        self.toolbar.addAction(act_copy_json)
        self.toolbar.addAction(act_save_json)
        self.toolbar.addAction(act_save_log)
        root.addWidget(self.toolbar)

        act_restart.triggered.connect(self._restart_job)
        act_clone.triggered.connect(self._clone_job)
        act_delete.triggered.connect(self._delete_job)
        act_cancel.triggered.connect(self._cancel_job)
        act_copy_json.triggered.connect(self._copy_json)
        act_save_json.triggered.connect(self._save_json)
        act_save_log.triggered.connect(self._save_logs)

        # Meta box
        meta_box = QGroupBox("Metadata")
        meta_form = QFormLayout()
        self.val_type = QLabel("—")
        self.val_device = QLabel("—")
        self.val_created = QLabel("—")
        self.val_progress = QLabel("—")
        meta_form.addRow("Type:", self.val_type)
        meta_form.addRow("Device:", self.val_device)
        meta_form.addRow("Created:", self.val_created)
        meta_form.addRow("Progress:", self.val_progress)
        meta_box.setLayout(meta_form)
        root.addWidget(meta_box)

        # JSON detail
        self.json_view = QTextEdit()
        self.json_view.setReadOnly(True)
        self.json_view.setPlaceholderText("Job JSON will appear here…")
        root.addWidget(self.json_view, 2)

        # Logs
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Live logs will appear here…")
        root.addWidget(self.log_view, 3)

        # Footer controls
        frow = QHBoxLayout()
        self.btn_start_stream = QPushButton("Start Log Stream")
        self.btn_stop_stream = QPushButton("Stop Log Stream")
        self.btn_refresh = QPushButton("Refresh Metadata")
        frow.addWidget(self.btn_start_stream)
        frow.addWidget(self.btn_stop_stream)
        frow.addStretch(1)
        frow.addWidget(self.btn_refresh)
        root.addLayout(frow)

        self.btn_start_stream.clicked.connect(self.start_log_stream)
        self.btn_stop_stream.clicked.connect(self.stop_log_stream)
        self.btn_refresh.clicked.connect(self._poll_job_meta)

        # start with stream controls disabled until a job is set
        self._set_controls_enabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_job(self, job: dict):
        """Bind the panel to a job and refresh UI."""
        self.current_job = job or {}
        self.current_job_id = (job or {}).get("id")
        self._render_job()
        # Start polling meta (safe even if stream is on; cheap GET)
        self._poll_timer.start()
        # enable controls
        self._set_controls_enabled(bool(self.current_job_id))

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _render_job(self):
        jid = self.current_job.get("id", "—")
        status = self.current_job.get("status", "—")
        jtype = self.current_job.get("type", "—")
        device = self.current_job.get("device", "—")
        created = self.current_job.get("created_at", "—")
        progress = self.current_job.get("progress", "—")

        self.lbl_title.setText(f"Job: {jid}")
        self.lbl_status.setText(f"Status: {status}")
        self.val_type.setText(str(jtype))
        self.val_device.setText(str(device))
        self.val_created.setText(str(created))
        self.val_progress.setText(str(progress))

        try:
            pretty = json.dumps(self.current_job, indent=2, ensure_ascii=False)
        except Exception:
            pretty = str(self.current_job)
        self.json_view.setPlainText(pretty)
        self.json_view.moveCursor(QTextCursor.Start)

    def _append_log(self, line: str):
        self.log_view.moveCursor(QTextCursor.End)
        self.log_view.insertPlainText(line.rstrip("\n") + "\n")
        self.log_view.moveCursor(QTextCursor.End)

    def _set_controls_enabled(self, enabled: bool):
        self.toolbar.setEnabled(enabled)
        self.btn_start_stream.setEnabled(enabled)
        self.btn_stop_stream.setEnabled(enabled)
        self.btn_refresh.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Metadata polling
    # ------------------------------------------------------------------
    def _poll_job_meta(self):
        if not self.current_job_id:
            return

        def _done(resp):
            job = resp.get("job") if isinstance(resp, dict) else None
            if job:
                self.current_job = job
                self.job_updated.emit(job)
                self._render_job()

        # Use ServerBridge generic GET helper if available; otherwise do a simple thread
        def _work():
            try:
                url = f"{self.server_url}/jobs/{self.current_job_id}"
                r = requests.get(url, timeout=6)
                if r.status_code == 200:
                    _done(r.json())
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    # Log streaming
    # ------------------------------------------------------------------
    @Slot()
    def start_log_stream(self):
        if not self.current_job_id:
            return
        if self._stream_thread and self._stream_thread.is_alive():
            self.message.emit("Log stream already running.")
            return
        self._stream_stop.clear()
        self.log_view.append(
            f"— Log stream started @ {datetime.now().strftime('%H:%M:%S')} —"
        )
        self._stream_thread = threading.Thread(
            target=self._stream_logs_worker, daemon=True
        )
        self._stream_thread.start()

    @Slot()
    def stop_log_stream(self):
        self._stream_stop.set()
        self.log_view.append(
            f"— Log stream stopped @ {datetime.now().strftime('%H:%M:%S')} —"
        )

    def _stream_logs_worker(self):
        """
        Tries Server-Sent Events or chunked streaming from:
          GET /jobs/{id}/stream   (preferred)
        Falls back to:
          GET /jobs/{id}/logs     (poll each second)
        """
        jid = self.current_job_id
        if not jid:
            return
        # Preferred stream endpoint
        url_stream = f"{self.server_url}/jobs/{jid}/stream"
        try:
            with requests.get(url_stream, stream=True, timeout=10) as r:
                if (
                    r.status_code == 200
                    and r.headers.get("Transfer-Encoding") == "chunked"
                ):
                    for chunk in r.iter_lines(decode_unicode=True):
                        if self._stream_stop.is_set():
                            return
                        if chunk:
                            self._append_log(chunk)
                    return
        except Exception:
            pass

        # Fallback: poll /logs every 1s
        url_logs = f"{self.server_url}/jobs/{jid}/logs"
        last_len = 0
        while not self._stream_stop.is_set():
            try:
                r = requests.get(url_logs, timeout=6)
                if r.status_code == 200:
                    txt = r.text or ""
                    if len(txt) > last_len:
                        self._append_log(txt[last_len:])
                        last_len = len(txt)
            except Exception:
                pass
            self._stream_stop.wait(1.0)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    @Slot()
    def _restart_job(self):
        if not self.current_job_id:
            return

        def _work():
            try:
                r = requests.post(
                    f"{self.server_url}/jobs/restart",
                    json={"job_id": self.current_job_id},
                    timeout=8,
                )
                self.message.emit(
                    "Restart requested."
                    if r.status_code == 200
                    else f"Restart failed: {r.status_code}"
                )
                self._poll_job_meta()
            except Exception as e:
                self.message.emit(f"Restart failed: {e}")

        threading.Thread(target=_work, daemon=True).start()

    @Slot()
    def _clone_job(self):
        if not self.current_job_id:
            return

        def _work():
            try:
                r = requests.post(
                    f"{self.server_url}/jobs/clone",
                    json={"job_id": self.current_job_id},
                    timeout=8,
                )
                self.message.emit(
                    "Clone requested."
                    if r.status_code == 200
                    else f"Clone failed: {r.status_code}"
                )
            except Exception as e:
                self.message.emit(f"Clone failed: {e}")

        threading.Thread(target=_work, daemon=True).start()

    @Slot()
    def _delete_job(self):
        if not self.current_job_id:
            return
        if (
            QMessageBox.question(self, "Delete Job", "Delete this job permanently?")
            != QMessageBox.Yes
        ):
            return

        def _work():
            try:
                r = requests.post(
                    f"{self.server_url}/jobs/delete",
                    json={"job_id": self.current_job_id},
                    timeout=8,
                )
                self.message.emit(
                    "Delete requested."
                    if r.status_code == 200
                    else f"Delete failed: {r.status_code}"
                )
            except Exception as e:
                self.message.emit(f"Delete failed: {e}")

        threading.Thread(target=_work, daemon=True).start()

    @Slot()
    def _cancel_job(self):
        if not self.current_job_id:
            return

        def _work():
            try:
                r = requests.post(
                    f"{self.server_url}/jobs/kill",
                    json={"job_id": self.current_job_id},
                    timeout=8,
                )
                self.message.emit(
                    "Cancel requested."
                    if r.status_code == 200
                    else f"Cancel failed: {r.status_code}"
                )
            except Exception as e:
                self.message.emit(f"Cancel failed: {e}")

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @Slot()
    def _copy_json(self):
        if not self.current_job:
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(
            json.dumps(self.current_job, indent=2, ensure_ascii=False)
        )
        self.message.emit("Job JSON copied to clipboard.")

    @Slot()
    def _save_json(self):
        if not self.current_job:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Job JSON",
            f"job_{self.current_job_id or 'unknown'}.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.current_job, f, indent=2, ensure_ascii=False)
            self.message.emit(f"Saved JSON → {path}")
        except Exception as e:
            self.message.emit(f"Save failed: {e}")

    @Slot()
    def _save_logs(self):
        if not self.current_job_id:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Logs", f"job_{self.current_job_id}_logs.txt", "Text (*.txt)"
        )
        if not path:
            return
        try:
            # Try direct log endpoint
            r = requests.get(
                f"{self.server_url}/jobs/{self.current_job_id}/logs", timeout=8
            )
            txt = r.text if r.status_code == 200 else self.log_view.toPlainText()
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
            self.message.emit(f"Saved Logs → {path}")
        except Exception as e:
            self.message.emit(f"Save failed: {e}")
