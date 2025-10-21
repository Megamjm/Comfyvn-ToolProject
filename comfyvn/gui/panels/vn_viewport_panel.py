from __future__ import annotations

from PySide6.QtGui import QAction
# comfyvn/gui/panels/vn_viewport_panel.py
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class VNViewportPanel(QWidget):
    """A placeholder viewport for VN runtime/preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("VNViewport Panel"))
