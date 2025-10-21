from __future__ import annotations

from PySide6.QtGui import QAction
# comfyvn/gui/panels/render_dashboard_panel.py
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class RenderDashboardPanel(QWidget):
    """Render queue and job stats (placeholder)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("RenderDashboard Panel"))
