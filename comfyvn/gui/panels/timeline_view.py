from PySide6.QtGui import QAction
# comfyvn/gui/panels/timeline_view.py.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from comfyvn.core.notifier import notifier

class TimelineView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TimelineView")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("TimelineView"))
        btn = QPushButton("Ping Log"); btn.clicked.connect(lambda: notifier.toast("info", "TimelineView ping"))
        lay.addWidget(btn)