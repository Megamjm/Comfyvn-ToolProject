from PySide6.QtGui import QAction
# comfyvn/gui/settings_ui.py
# [Main window update chat]
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SettingsUI(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Settings (stub)"))
