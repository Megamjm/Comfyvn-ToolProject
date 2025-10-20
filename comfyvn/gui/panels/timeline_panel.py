from PySide6.QtGui import QAction

# comfyvn/gui/panels/timeline_panel.py  [Studio-090]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QDockWidget
from PySide6.QtCore import Qt

class TimelinePanel(QDockWidget):
    def __init__(self):
        super().__init__("Timeline")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        w = QWidget(); lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Timeline / Graph (placeholder)"))
        self.setWidget(w)