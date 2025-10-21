import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

# comfyvn/gui/panels/gpu_panel.py  [Studio-089]
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config.baseurl_authority import default_base_url


class GPUPanel(QDockWidget):
    def __init__(self, base: str | None = None):
        super().__init__("GPU/Resources")
        self.base = (base or default_base_url()).rstrip("/")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        btn = QPushButton("GET /system/metrics")
        btn.clicked.connect(self.refresh)
        lay.addWidget(QLabel("System & GPU metrics"))
        lay.addWidget(btn)
        lay.addWidget(self.out)
        self.setWidget(w)

    def refresh(self):
        try:
            r = requests.get(f"{self.base}/system/metrics", timeout=2)
            self.out.setPlainText(r.text)
        except Exception as e:
            self.out.setPlainText(str(e))
