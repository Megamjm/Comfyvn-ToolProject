from PySide6.QtGui import QAction


class UIState:
    def __init__(self):
        self.project_path = None

    def load_project(self, path: str):
        self.project_path = path
