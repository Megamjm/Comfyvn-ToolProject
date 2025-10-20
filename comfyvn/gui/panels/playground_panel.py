from PySide6.QtGui import QAction

# comfyvn/gui/panels/playground_panel.py  [Studio-090]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit, QLabel, QDockWidget
from PySide6.QtCore import Qt
import requests

class PlaygroundPanel(QDockWidget):
    def __init__(self, base="http://127.0.0.1:8001"):
        super().__init__("Playground")
        self.base = base
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        w = QWidget(); lay = QVBoxLayout(w)
        self.out = QTextEdit(); self.out.setReadOnly(True)
        btn = QPushButton("GET /system/metrics")
        btn.clicked.connect(self.ping)
        lay.addWidget(QLabel("Quick Calls")); lay.addWidget(btn); lay.addWidget(self.out)
        self.setWidget(w)

    def ping(self):
        try:
            r = requests.get(f"{self.base}/system/metrics", timeout=2)
            self.out.setPlainText(r.text)
        except Exception as e:
            self.out.setPlainText(str(e))