from PySide6.QtGui import QAction
# comfyvn/gui/panels/settings_appearance_view.py.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from comfyvn.core.notifier import notifier


class SettingsAppearanceView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SettingsAppearanceView")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("SettingsAppearanceView"))
        btn = QPushButton("Ping Log")
        btn.clicked.connect(
            lambda: notifier.toast("info", "SettingsAppearanceView ping")
        )
        lay.addWidget(btn)
