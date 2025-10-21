from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
# comfyvn/gui/panels/studio_center.py
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)


class StudioCenter(QWidget):
    """Central dashboard dock — quick launch, status, recent files."""

    def __init__(self, bridge=None, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        v = QVBoxLayout(self)
        self.title = QLabel("ComfyVN Studio Center")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setProperty("accent", True)
        v.addWidget(self.title)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        v.addWidget(self.log_box, 1)
        self.btn_refresh = QPushButton("Refresh Status")
        v.addWidget(self.btn_refresh)

        self.btn_refresh.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.log_box.append(
            f"[{datetime.now().strftime('%H:%M:%S')}] Studio Center active."
        )
