from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/windows/importers/vn_importer_window.py  [Phase 1.20]
from pathlib import Path

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox
from PySide6.QtCore import QTimer

from comfyvn.gui.services.server_bridge import ServerBridge

class VNImporterWindow(QDialog):
    def __init__(self, parent=None, bridge: ServerBridge | None = None):
        super().__init__(parent)
        self.setWindowTitle("VN Importer")
        self.bridge = bridge or ServerBridge()
        self._current_job_id: str | None = None
        self._pending_name: str = ""
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1500)
        self._poll_timer.timeout.connect(self._poll_job)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Import .pak / zip visual novels.\nThis will extract assets, scenarios, characters."))
        btn = QPushButton("Choose File…")
        btn.clicked.connect(self._choose)
        lay.addWidget(btn)
        self.status_label = QLabel("")
        lay.addWidget(self.status_label)

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select VN Package", "", "Packages (*.pak *.zip);;All (*.*)")
        if not path: return
        name = Path(path).name
        self._pending_name = name
        self.status_label.setText(f"Queuing import for {name}…")
        self._current_job_id = None

        def _handle(result):
            QTimer.singleShot(0, lambda: self._on_enqueued(result, path, name))

        self.bridge.post("/vn/import", {"path": path}, cb=_handle)

    def _on_enqueued(self, result: dict, path: str, name: str):
        if not result.get("ok"):
            msg = result.get("error") or f"Request failed (status {result.get('status')})"
            QMessageBox.warning(self, "Import Failed", msg)
            self.status_label.setText(f"Failed to queue {name}: {msg}")
            return

        data = result.get("data") or {}
        if not isinstance(data, dict) or not data.get("ok"):
            detail = data.get("detail") if isinstance(data, dict) else str(data)
            QMessageBox.warning(self, "Import Failed", str(detail))
            self.status_label.setText(f"Server rejected {name}: {detail}")
            return

        job = data.get("job") or {}
        job_id = job.get("id")
        if not job_id:
            # fallback to immediate summary (blocking mode response)
            summary = data.get("import") or {}
            self._handle_summary(name, summary)
            return

        self._current_job_id = job_id
        self.status_label.setText(f"Import queued ({job_id[:8]}) — awaiting completion…")
        self._poll_timer.start()
        self._poll_job()

    def _handle_summary(self, name: str, summary: dict):
        scenes = len(summary.get("scenes", []))
        characters = len(summary.get("characters", []))
        assets = len(summary.get("assets", []))
        warnings = summary.get("warnings", [])
        message = f"Imported {name}: {scenes} scene(s), {characters} character(s), {assets} asset(s)."
        if warnings:
            message += f"\nWarnings: {len(warnings)}"
        QMessageBox.information(self, "Import Complete", message)
        self.status_label.setText(message)

    def _poll_job(self):
        if not self._current_job_id:
            self._poll_timer.stop()
            return

        def _handle(result):
            QTimer.singleShot(0, lambda: self._on_job_status(result))

        self.bridge.get_json(f"/jobs/status/{self._current_job_id}", cb=_handle)

    def _on_job_status(self, result: dict):
        if not self._current_job_id:
            self._poll_timer.stop()
            return
        if not result.get("ok"):
            # keep polling but surface warning once
            msg = result.get("error") or f"Status request failed ({result.get('status')})"
            self.status_label.setText(f"Waiting on {self._pending_name}: {msg}")
            return

        data = result.get("data") or {}
        if not isinstance(data, dict):
            self.status_label.setText(f"Waiting on {self._pending_name}: invalid job response")
            return

        job = data.get("job") or {}
        status = job.get("status")
        meta = job.get("meta") or {}

        if status == "done":
            self._poll_timer.stop()
            self._current_job_id = None
            summary = meta.get("result") or {}
            self._handle_summary(self._pending_name or "package", summary)
            return

        if status == "error":
            self._poll_timer.stop()
            self._current_job_id = None
            error_msg = job.get("message") or meta.get("error") or "Import failed"
            QMessageBox.warning(self, "Import Failed", error_msg)
            self.status_label.setText(f"{self._pending_name} failed: {error_msg}")
            return

        progress = job.get("progress") or 0.0
        self.status_label.setText(
            f"Importing {self._pending_name}… status={status} progress={int(progress*100)}%"
        )
