from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
# comfyvn/gui/panels/extensions_panel.py  [Studio-090]
from PySide6.QtWidgets import (QDockWidget, QLabel, QListWidget, QPushButton,
                               QVBoxLayout, QWidget)


class ExtensionsPanel(QDockWidget):
    def __init__(self):
        super().__init__("Extensions")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.list = QListWidget()
        lay.addWidget(QLabel("Installed Extensions:"))
        lay.addWidget(self.list)
        btn = QPushButton("Refresh")
        btn.clicked.connect(self.refresh)
        lay.addWidget(btn)
        self.setWidget(w)
        self.refresh()

    def refresh(self):
        self.list.clear()
        # placeholder: later wire to extension registry
        for name in ["SillyTavern Bridge", "ComfyUI Bridge", "Ren'Py Exporter"]:
            self.list.addItem(name)
