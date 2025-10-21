from PySide6.QtGui import QAction
# comfyvn/gui/widgets/task_manager_dock.py
# [Main window update chat] — minimal stub to satisfy imports
from PySide6.QtWidgets import QDockWidget, QLabel, QVBoxLayout, QWidget


class TaskManagerDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Tasks", parent)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Task Manager (stub)"))
        self.setWidget(w)
