from PySide6.QtGui import QAction
# comfyvn/gui/panels/view_editor_view.py.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from comfyvn.core.notifier import notifier


class ViewEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ViewEditor")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("ViewEditor"))
        btn = QPushButton("Ping Log")
        btn.clicked.connect(lambda: notifier.toast("info", "ViewEditor ping"))
        lay.addWidget(btn)
