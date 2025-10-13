# comfyvn/gui/components/progress_overlay.py
# [🎨 GUI Code Production Chat]
# Phase 3.3 – Progress Overlay Widget

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt, QTimer


class ProgressOverlay(QWidget):
    """Semi-transparent overlay with progress indication."""

    def __init__(self, parent=None, text="Processing...", duration_ms=0):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            """
            QWidget {
                background-color: rgba(0, 0, 0, 180);
                color: white;
                border-radius: 12px;
            }
        """
        )

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # indeterminate
        layout.addWidget(self.bar)

        self.timer = None
        if duration_ms > 0:
            self.timer = QTimer(self)
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.hide)
            self.timer.start(duration_ms)

    def show_message(self, text):
        self.label.setText(text)
        self.show()

    def hide_overlay(self):
        self.hide()
