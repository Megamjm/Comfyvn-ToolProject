# comfyvn/gui/main_window/spaces_bar.py
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar


class SpacesBar(QToolBar):
    """Top bar with workspace shortcuts."""

    def __init__(self, main):
        super().__init__("Spaces")
        self.main = main
        self.setMovable(False)
        self.setObjectName("SpacesBar")
        self.actions_map = {}
        for lbl in ["Editor", "Render", "Import", "GPU", "Logs"]:
            a = QAction(lbl, self)
            a.setCheckable(True)
            a.triggered.connect(lambda _, n=lbl: self._switch(n))
            self.addAction(a)
            self.actions_map[lbl.lower()] = a
        self._highlight("editor")

    def _switch(self, name: str):
        self.main.open_space(name)
        self._highlight(name)

    def _highlight(self, name: str):
        for n, a in self.actions_map.items():
            a.setChecked(n == name.lower())
