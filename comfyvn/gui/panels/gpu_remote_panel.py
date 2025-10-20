from PySide6.QtGui import QAction

# comfyvn/gui/panels/gpu_remote_panel.py  [Studio-090]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit, QDockWidget, QLineEdit, QHBoxLayout
from PySide6.QtCore import Qt
import requests

class GPURemotePanel(QDockWidget):
    def __init__(self, endpoints: list[str] | None = None):
        super().__init__("GPU / Remote")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.endpoints = endpoints or []
        w = QWidget(); lay = QVBoxLayout(w)
        self.inp = QLineEdit(",".join(self.endpoints))
        self.out = QTextEdit(); self.out.setReadOnly(True)
        hb = QHBoxLayout(); btn_probe = QPushButton("Probe"); btn_probe.clicked.connect(self.probe)
        hb.addWidget(btn_probe)
        lay.addWidget(QLabel("Comma-separated endpoints (http[s]://host:port/metrics or /health):"))
        lay.addWidget(self.inp); lay.addLayout(hb); lay.addWidget(self.out)
        self.setWidget(w)

    def probe(self):
        self.out.clear()
        eps = [e.strip() for e in self.inp.text().split(",") if e.strip()]
        for ep in eps:
            url = ep
            if url.endswith("/"): url = url[:-1]
            # try /metrics then /health then /
            tried = []
            for suffix in ("/system/metrics","/metrics","/health","/"):
                u = f"{url}{suffix}"
                try:
                    r = requests.get(u, timeout=2)
                    self.out.append(f"{u} -> {r.status_code}\n{r.text[:400]}\n---")
                    break
                except Exception as e:
                    tried.append(f"{u} ❌ {e}")
            if tried:
                self.out.append("\n".join(tried) + "\n---")