import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
# comfyvn/gui/panels/gpu_local_panel.py  [Studio-090]
from PySide6.QtWidgets import (QDockWidget, QLabel, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)


class GPULocalPanel(QDockWidget):
    def __init__(self, base="http://127.0.0.1:8001"):
        super().__init__("GPU / Local")
        self.base = base
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        btn = QPushButton("Refresh")
        btn.clicked.connect(self.refresh)
        lay.addWidget(QLabel("Local System Metrics"))
        lay.addWidget(btn)
        lay.addWidget(self.out)
        self.setWidget(w)
        self.refresh()

    def refresh(self):
        try:
            r = requests.get(f"{self.base}/system/metrics", timeout=2)
            self.out.setPlainText(r.text)
        except Exception as e:
            self.out.setPlainText(str(e))
