from __future__ import annotations

from PySide6.QtGui import QAction
# comfyvn/gui/panels/importer_panel.py
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ImporterPanel(QWidget):
    """Basic importer placeholder (VN/Manga/Assets)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Importer Panel"))
