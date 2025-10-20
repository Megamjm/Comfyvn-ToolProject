from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/panels/gpu_manager_panel.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class GPUManagerPanel(QWidget):
    """GPU manager placeholder panel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("GPUManager Panel"))