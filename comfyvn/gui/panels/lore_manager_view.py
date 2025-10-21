from PySide6.QtGui import QAction
# comfyvn/gui/panels/lore_manager_view.py.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from comfyvn.core.notifier import notifier


class LoreManagerView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoreManagerView")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("LoreManagerView"))
        btn = QPushButton("Ping Log")
        btn.clicked.connect(lambda: notifier.toast("info", "LoreManagerView ping"))
        lay.addWidget(btn)
