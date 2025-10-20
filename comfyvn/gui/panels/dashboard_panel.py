from PySide6.QtGui import QAction
# comfyvn/gui/panels/dashboard_panel.py
# [COMFYVN Architect | v2.4 | this chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget, QHBoxLayout
from PySide6.QtCore import Signal

class DashboardPanel(QWidget):
    """Simple dashboard: Active project + Recent projects quick open."""
    project_opened = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(12,12,12,12); root.setSpacing(8)

        self.lbl = QLabel("<b>ComfyVN Studio Dashboard</b>")
        self.lbl_active = QLabel("Active project: (none)")
        btns = QHBoxLayout()
        self.btn_new = QPushButton("New Project")
        self.btn_open = QPushButton("Open Project…")
        btns.addWidget(self.btn_new); btns.addWidget(self.btn_open)

        self.recent = QListWidget()
        self.recent.setMinimumHeight(160)

        root.addWidget(self.lbl)
        root.addWidget(self.lbl_active)
        root.addLayout(btns)
        root.addWidget(QLabel("Recent:"))
        root.addWidget(self.recent, 1)

        self.btn_new.clicked.connect(self._new_project)
        self.btn_open.clicked.connect(self._open_project)
        self.recent.itemDoubleClicked.connect(self._open_recent)

        self._refresh()

    def _refresh(self):
        try:
            from comfyvn.core.workspace_manager import get_last_project, list_recent
            active = get_last_project() or "(none)"
            self.lbl_active.setText(f"Active project: {active}")
            self.recent.clear()
            for pid in (list_recent() or []):
                self.recent.addItem(pid)
        except Exception:
            pass

    def _new_project(self):
        try:
            from comfyvn.core.workspace_manager import create_new
            pid = create_new()
            if pid: self.project_opened.emit(pid)
        except Exception:
            pass

    def _open_project(self):
        try:
            from comfyvn.core.workspace_manager import choose_and_open
            pid = choose_and_open()
            if pid: self.project_opened.emit(pid)
        except Exception:
            pass

    def _open_recent(self, item):
        pid = item.text()
        if pid: self.project_opened.emit(pid)