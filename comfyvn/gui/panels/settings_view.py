from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                               QStackedWidget, QWidget)


class SettingsView(QWidget):
    def __init__(self, state):
        super().__init__()
        root = QHBoxLayout(self)
        self.nav = QListWidget()
        self.nav.addItems(["General", "Render/Grid"])
        root.addWidget(self.nav, 1)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 4)
        self.stack.addWidget(QLabel("General — placeholder"))
        self.stack.addWidget(QLabel("Render/Grid — provider manager placeholder"))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
