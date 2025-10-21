import requests
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QStatusBar


class StatusBarMixin:
    def _init_status(self):
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        self._lbl_server = QLabel("Server: â³")
        self._lbl_cpu = QLabel("CPU: â€“")
        self._lbl_mem = QLabel("RAM: â€“")
        self._lbl_gpu = QLabel("GPU: â€“")
        for w in (self._lbl_server, self._lbl_cpu, self._lbl_mem, self._lbl_gpu):
            sb.addPermanentWidget(w)

        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._poll_metrics)
        self._timer.start()

    def _poll_metrics(self):
        base = "http://127.0.0.1:8001"
        try:
            r = requests.get(f"{base}/system/metrics", timeout=1.0)
            if r.ok:
                m = r.json()
                self._lbl_server.setText("Server: ðŸŸ¢")
                self._lbl_cpu.setText(f"CPU: {m.get('cpu','-')}%")
                self._lbl_mem.setText(f"RAM: {m.get('mem','-')}%")
                gpus = m.get("gpus") or []
                if gpus:
                    g = gpus[0]
                    self._lbl_gpu.setText(
                        f"GPU: {g.get('util','-')}% {g.get('mem_used','-')}/{g.get('mem_total','-')}MB"
                    )
                else:
                    self._lbl_gpu.setText("GPU: â€“")
            else:
                self._down()
        except Exception:
            self._down()

    def _down(self):
        self._lbl_server.setText("Server: ðŸ”´")
        self._lbl_cpu.setText("CPU: â€“")
        self._lbl_mem.setText("RAM: â€“")
        self._lbl_gpu.setText("GPU: â€“")
