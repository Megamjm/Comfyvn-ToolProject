from PySide6.QtGui import QAction
# comfyvn/gui/panels/vn_preview_view.py.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from comfyvn.core.notifier import notifier


class VNPreviewView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VNPreviewView")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("VNPreviewView"))
        btn = QPushButton("Ping Log")
        btn.clicked.connect(lambda: notifier.toast("info", "VNPreviewView ping"))
        lay.addWidget(btn)
