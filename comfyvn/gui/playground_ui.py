from PySide6.QtGui import QAction
# comfyvn/gui/playground_ui.py
# [Main window update chat]
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaygroundUI(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Playground (stub)"))
