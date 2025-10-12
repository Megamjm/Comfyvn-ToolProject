# comfyvn/gui/components/task_console_window.py
# [🎨 GUI Code Production Chat]
# Phase 3.6 – Live job console (per-task output monitor)

import threading, requests, time
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel, QHBoxLayout
)
from PySide6.QtCore import Qt, QTimer


class TaskConsoleWindow(QDialog):
    """Floating live log viewer for a backend job."""

    def __init__(self, server_url, job_id, parent=None):
        super().__init__(parent)
        self.server_url = server_url.rstrip("/")
        self.job_id = job_id
        self.setWindowTitle(f"Job Console – {job_id}")
        self.resize(700, 400)

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Connecting...")
        layout.addWidget(self.status_label)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("background:#111;color:#0f0;font-family:monospace;")
        layout.addWidget(self.text)

        btns = QHBoxLayout()
        self.btn_pause = QPushButton("Pause")
        self.btn_clear = QPushButton("Clear")
        self.btn_close = QPushButton("Close")
        btns.addWidget(self.btn_pause)
        btns.addWidget(self.btn_clear)
        btns.addWidget(self.btn_close)
        layout.addLayout(btns)

        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_clear.clicked.connect(lambda: self.text.clear())
        self.btn_close.clicked.connect(self.close)

        self._paused = False
        self._stop_flag = False
        self.timer = QTimer()
        self.timer.timeout.connect(self._poll)
        self.timer.start(2000)

        self.show()

    # ---------------------------------------------------------
    def toggle_pause(self):
        self._paused = not self._paused
        self.btn_pause.setText("Resume" if self._paused else "Pause")

    def closeEvent(self, event):
        self._stop_flag = True
        event.accept()

    def _poll(self):
        if self._paused or self._stop_flag:
            return
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            r = requests.get(f"{self.server_url}/jobs/log", params={"id": self.job_id}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                logs = data.get("lines", [])
                self._update_text(logs)
                status = data.get("status", "")
                self.status_label.setText(f"Status: {status}")
        except Exception:
            pass

    def _update_text(self, logs):
        if not logs:
            return
        joined = "\n".join(logs)
        self.text.append(joined)
        self.text.moveCursor(self.text.textCursor().End)