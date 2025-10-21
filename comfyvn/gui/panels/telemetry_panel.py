from __future__ import annotations

import os

import requests
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction

# comfyvn/gui/panels/telemetry_panel.py
from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from comfyvn.config.baseurl_authority import default_base_url
from comfyvn.config.runtime_paths import logs_dir


class TelemetryPanel(QWidget):
    def __init__(self, base: str | None = None):
        super().__init__()
        self.base = (base or default_base_url()).rstrip("/")
        v = QVBoxLayout(self)
        self.lbl = QLabel("System Metrics", self)
        v.addWidget(self.lbl)
        self.text = QTextEdit(self)
        self.text.setReadOnly(True)
        v.addWidget(self.text, 1)
        self._request_inflight = False
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self):
        if self._request_inflight:
            return
        self._request_inflight = True
        try:
            try:
                r = requests.get(self.base + "/system/metrics", timeout=2.0)
                if r.ok:
                    m = r.json()
                    self.lbl.setText(
                        f"CPU {m.get('cpu')}% | MEM {m.get('mem')}% | DISK {m.get('disk')}% | GPUs {len(m.get('gpus',[]))}"
                    )
                else:
                    self.lbl.setText("System Metrics (offline)")
            except Exception:
                self.lbl.setText("System Metrics (offline)")
            # tail logs
            parts = []
            root = logs_dir()
            if root.exists():
                files = sorted(root.glob("*.log"), key=lambda p: p.name)[-3:]
                for fn in files:
                    try:
                        tail = "".join(
                            fn.read_text(encoding="utf-8", errors="ignore").splitlines(
                                keepends=True
                            )[-20:]
                        )
                        parts.append(f"--- {fn.name} ---\n{tail}")
                    except Exception:
                        pass
            self.text.setPlainText("\n".join(parts))
        finally:
            self._request_inflight = False
