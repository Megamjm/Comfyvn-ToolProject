from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CentralSpace(QWidget):
    """Placeholder central canvas kept for legacy shells."""

    def __init__(self, open_assets=None, open_timeline=None, open_logs=None):
        super().__init__()
        self.setObjectName("CentralSpace")
        layout = QVBoxLayout(self)

        title = QLabel("Central Space")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        hint = QLabel(
            "Use the View menu to open panels around this central space.\n"
            "Use File → New/Load Project to manage your workspace."
        )
        layout.addWidget(hint)

        row = QHBoxLayout()
        assets_btn = QPushButton("Open Assets")
        assets_btn.clicked.connect(open_assets or (lambda: None))
        timeline_btn = QPushButton("Open Timeline")
        timeline_btn.clicked.connect(open_timeline or (lambda: None))
        logs_btn = QPushButton("Show Logs")
        logs_btn.clicked.connect(open_logs or (lambda: None))
        row.addWidget(assets_btn)
        row.addWidget(timeline_btn)
        row.addWidget(logs_btn)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(10)
