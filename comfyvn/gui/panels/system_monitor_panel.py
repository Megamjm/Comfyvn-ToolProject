from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/panels/system_monitor_panel.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class SystemMonitorPanel(QWidget):
    """System monitor placeholder panel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("SystemMonitor Panel"))