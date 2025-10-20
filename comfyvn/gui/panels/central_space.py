from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt

class CentralSpace(QWidget):
    """A simple central canvas that can host VN preview / data status.
    Leaves docking for side/bottom panels (Assets, GPU, Logs) intact."""
    def __init__(self, open_assets=None, open_timeline=None, open_logs=None):
        super().__init__()
        self.setObjectName("CentralSpace")
        v = QVBoxLayout(self)
        title = QLabel("Central Space")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        v.addWidget(title)

        hint = QLabel("Use the View menu to open panels around this central space.\n"
                      "Use File → New/Load Project to manage your workspace.")
        v.addWidget(hint)

        row = QHBoxLayout()
        b1 = QPushButton("Open Assets"); b1.clicked.connect(open_assets or (lambda: None))
        b2 = QPushButton("Open Timeline"); b2.clicked.connect(open_timeline or (lambda: None))
        b3 = QPushButton("Show Logs"); b3.clicked.connect(open_logs or (lambda: None))
        row.addWidget(b1); row.addWidget(b2); row.addWidget(b3); row.addStretch(1)
        v.addLayout(row)
        v.addStretch(10)
