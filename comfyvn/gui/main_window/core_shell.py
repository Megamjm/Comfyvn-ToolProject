from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QDockWidget, QLabel, QMainWindow, QVBoxLayout,
                               QWidget)


class DockManager:
    def __init__(self, window: QMainWindow):
        self.window = window
        self._docks = []

    def dock(self, widget: QWidget, title: str, area=Qt.RightDockWidgetArea):
        dock = QDockWidget(title, self.window)
        dock.setWidget(widget)
        self.window.addDockWidget(area, dock)
        self._docks.append(dock)
        return dock


class Shell(QMainWindow):
    def __init__(self, title="ComfyVN Studio"):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1280, 800)

        self._central = QWidget()
        self.setCentralWidget(self._central)
        lay = QVBoxLayout(self._central)
        lay.setContentsMargins(8, 8, 8, 8)

        self.lbl_info = QLabel("Ready")
        lay.addWidget(self.lbl_info)

        self.dockman = DockManager(self)

        self.setStyleSheet(
            """
        QMainWindow { background: #171a1f; color: #e8eaed; }
        QLabel { color: #e8eaed; }
        QDockWidget { background: #1f232b; color: #e8eaed; }
        QToolBar, QMenuBar, QStatusBar { background: #20242c; color: #e8eaed; }
        """
        )
