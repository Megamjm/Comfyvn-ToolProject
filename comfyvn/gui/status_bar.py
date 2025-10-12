# comfyvn/gui/components/status_bar.py
# 🧩 ComfyVN StatusBar Component
# Provides unified, color-coded feedback across all GUI systems.

from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QColor, QPalette


class StatusBar(QLabel):
    """Reusable status indicator widget with color feedback."""

    def __init__(self, default_text="Ready"):
        super().__init__(default_text)
        self.setAutoFillBackground(True)
        self.set_status("idle", default_text)

    def set_status(self, state: str, message: str):
        """Update message and background color based on state."""
        colors = {
            "success": QColor(46, 204, 113),   # green
            "warning": QColor(241, 196, 15),   # yellow
            "error": QColor(231, 76, 60),      # red
            "idle": QColor(149, 165, 166),     # gray
        }
        color = colors.get(state, colors["idle"])

        palette = self.palette()
        palette.setColor(QPalette.Window, color)
        self.setPalette(palette)
        self.setText(f" {message}")