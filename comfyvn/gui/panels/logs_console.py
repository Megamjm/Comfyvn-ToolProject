from PySide6.QtGui import QAction

# comfyvn/gui/panels/logs_console.py  [Studio-090]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QDockWidget
from PySide6.QtCore import Qt

class LogsConsole(QDockWidget):
    def __init__(self):
        super().__init__("Logs")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        w = QWidget(); lay = QVBoxLayout(w)
        self.out = QTextEdit(); self.out.setReadOnly(True)
        lay.addWidget(self.out); self.setWidget(w)
    def append(self, text: str):
        self.out.append(text)