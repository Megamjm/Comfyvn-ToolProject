# comfyvn/gui/components/status_widget.py
# 🎨 ComfyVN Status Indicator Widget — Phase 3.3-H
# Displays LED-style indicators for system connections and performance metrics.
# [🎨 GUI Code Production Chat]

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolTip
from PySide6.QtGui import QColor, QPixmap, QPainter
from PySide6.QtCore import Qt


class StatusWidget(QWidget):
    """Compact row of colored indicators for server, AI, and system state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 2, 4, 2)
        self.layout.setSpacing(6)
        self.indicators = {}

    # ------------------------------------------------------------------
    # Indicator Management
    # ------------------------------------------------------------------
    def add_indicator(self, name: str, tooltip: str = ""):
        """Create a new indicator if not present."""
        if name in self.indicators:
            return
        lbl = QLabel()
        lbl.setPixmap(self._make_pix("gray"))
        lbl.setToolTip(tooltip)
        self.layout.addWidget(lbl)
        self.indicators[name] = lbl

    def update_indicator(self, name: str, state: str, tooltip: str = ""):
        """Update LED color and tooltip by state."""
        color = self._state_to_color(state)
        if name not in self.indicators:
            self.add_indicator(name)
        lbl = self.indicators[name]
        lbl.setPixmap(self._make_pix(color))
        if tooltip:
            lbl.setToolTip(tooltip)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _make_pix(self, color: str):
        pix = QPixmap(14, 14)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.black)
        painter.drawEllipse(1, 1, 12, 12)
        painter.end()
        return pix

    def _state_to_color(self, state: str):
        mapping = {
            "online": "#00cc66",
            "busy": "#ffaa00",
            "warn": "#ffcc00",
            "offline": "#cc3333",
            "error": "#ff0000",
            "idle": "#888888",
        }
        return mapping.get(state, "#888888")

    # ------------------------------------------------------------------
    def clear(self):
        """Remove all indicators."""
        for _, lbl in self.indicators.items():
            self.layout.removeWidget(lbl)
            lbl.deleteLater()
        self.indicators.clear()
