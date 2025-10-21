from PySide6.QtGui import QAction
# comfyvn/gui/panels/lora_manager_view.py.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from comfyvn.core.notifier import notifier


class LoraManagerView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoraManagerView")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("LoraManagerView"))
        btn = QPushButton("Ping Log")
        btn.clicked.connect(lambda: notifier.toast("info", "LoraManagerView ping"))
        lay.addWidget(btn)
