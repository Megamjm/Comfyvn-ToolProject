import json

import requests
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QDialog, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTextEdit, QVBoxLayout)


class OffloadDialog(QDialog):
    def __init__(self, parent=None, base="http://127.0.0.1:8001"):
        super().__init__(parent)
        self.base = base
        self.setWindowTitle("Offload Job")
        self.setMinimumSize(400, 300)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Remote Endpoint:"))
        self.endpoint = QLineEdit("https://api.runpod.io")
        lay.addWidget(self.endpoint)
        lay.addWidget(QLabel("Payload (JSON):"))
        self.text = QTextEdit('{"prompt": "test render"}')
        lay.addWidget(self.text, 1)
        b = QPushButton("Send")
        lay.addWidget(b)
        b.clicked.connect(self.send)

    def send(self):
        try:
            payload = json.loads(self.text.toPlainText())
        except Exception as e:
            QMessageBox.warning(self, "JSON", str(e))
            return
        endpoint = self.endpoint.text().strip()
        try:
            r = requests.post(
                self.base + "/render/offload",
                json={"endpoint": endpoint, "payload": payload},
                timeout=10,
            )
            QMessageBox.information(self, "Result", str(r.json()))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
