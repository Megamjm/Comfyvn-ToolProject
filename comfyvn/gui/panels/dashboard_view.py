from PySide6.QtGui import QAction
# comfyvn/gui/panels/dashboard_view.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit
from PySide6.QtCore import Signal
class DashboardView(QWidget):
    project_opened = Signal(str)
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Dashboard • Open/Create Project"))
        self.inp = QLineEdit(); self.inp.setPlaceholderText("project_id"); lay.addWidget(self.inp)
        btn = QPushButton("Open"); lay.addWidget(btn)
        btn.clicked.connect(self._emit)
    def _emit(self):
        pid = self.inp.text().strip() or "demo"
        self.project_opened.emit(pid)