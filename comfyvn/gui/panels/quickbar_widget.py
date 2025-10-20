from PySide6.QtGui import QAction
# comfyvn/gui/panels/quickbar_widget.py
# [COMFYVN Architect | v1.2 | this chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QSizePolicy
from PySide6.QtCore import Qt

class QuickBar(QWidget):
    """Vertical strip of buttons to toggle common docks."""
    def __init__(self, entries=None, on_click=None):
        super().__init__()
        self.setObjectName("QuickBar")
        self.setFixedWidth(42)
        self.on_click = on_click or (lambda name: None)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4,4,4,4); lay.setSpacing(6)
        self.buttons = []
        for name, text, tip in (entries or []):
            b = QPushButton(text)
            b.setToolTip(tip or name)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setFixedHeight(32)
            b.clicked.connect(lambda _=False, n=name: self.on_click(n))
            lay.addWidget(b)
            self.buttons.append(b)
        lay.addStretch(1)