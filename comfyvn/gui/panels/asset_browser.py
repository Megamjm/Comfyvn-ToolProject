from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
# comfyvn/gui/panels/asset_browser.py  [Studio-090]
from PySide6.QtWidgets import (QDockWidget, QLabel, QListWidget, QVBoxLayout,
                               QWidget)


class AssetBrowser(QDockWidget):
    def __init__(self, base="assets"):
        super().__init__("Assets")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.lbl = QLabel("Assets")
        self.list = QListWidget()
        lay.addWidget(self.lbl)
        lay.addWidget(self.list)
        self.setWidget(w)
        self.base = Path(base)
        self.refresh()

    def refresh(self):
        self.list.clear()
        if not self.base.exists():
            return
        for p in self.base.rglob("*"):
            if p.is_file():
                self.list.addItem(str(p))
