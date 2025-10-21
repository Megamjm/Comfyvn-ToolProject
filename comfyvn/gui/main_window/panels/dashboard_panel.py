import requests
from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)


class DashboardPanel(QWidget):
    project_opened = Signal(str)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        title = QLabel("Dashboard")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        v.addWidget(title)

        self.lbl_health = QLabel("Server: â³")
        self.lbl_cpu = QLabel("CPU: â€“")
        self.lbl_mem = QLabel("RAM: â€“")
        self.lbl_disk = QLabel("Disk: â€“")
        for w in (self.lbl_health, self.lbl_cpu, self.lbl_mem, self.lbl_disk):
            v.addWidget(w)

        row = QHBoxLayout()
        b1 = QPushButton("Open Last Project")
        b1.clicked.connect(lambda: self.project_opened.emit("default-project"))
        row.addWidget(b1)
        b2 = QPushButton("Open Settings")
        row.addWidget(b2)
        v.addLayout(row)

        self._poll_inflight = False
        self._timer = QTimer(self)
        self._timer.setInterval(2500)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def _poll(self):
        if self._poll_inflight:
            return
        self._poll_inflight = True
        base = "http://127.0.0.1:8001"
        try:
            r = requests.get(f"{base}/system/metrics", timeout=2.0)
            if r.ok:
                m = r.json()
                self.lbl_health.setText("Server: ðŸŸ¢")
                self.lbl_cpu.setText(f"CPU: {m.get('cpu','-')}%")
                self.lbl_mem.setText(f"RAM: {m.get('mem','-')}%")
                self.lbl_disk.setText(f"Disk: {m.get('disk','-')}%")
            else:
                self._down()
        except Exception:
            self._down()
        finally:
            self._poll_inflight = False

    def _down(self):
        self.lbl_health.setText("Server: ðŸ”´")
        self.lbl_cpu.setText("CPU: â€“")
        self.lbl_mem.setText("RAM: â€“")
        self.lbl_disk.setText("Disk: â€“")
