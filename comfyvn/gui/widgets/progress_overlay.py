# comfyvn/gui/components/progress_overlay.py
# [🎨 GUI Code Production Chat]
# Semi-transparent overlay with progress label for long-running tasks.

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar


class ProgressOverlay(QWidget):
    """Overlay widget shown during background jobs."""

    def __init__(self, parent=None, text="Processing...", cancellable=False):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not cancellable)
        self.setWindowFlags(Qt.SubWindow)
        self.setStyleSheet(
            """
            background-color: rgba(0, 0, 0, 128);
            color: white;
            border-radius: 10px;
        """
        )

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        self.label = QLabel(text)
        self.label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)

        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        self.setLayout(layout)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse)
        self._pulse_dir = 1

    def start(self, pulse=True):
        """Show overlay and start animation."""
        self.show()
        if pulse:
            self._pulse_timer.start(50)

    def stop(self):
        self._pulse_timer.stop()
        self.hide()

    def _pulse(self):
        val = self.bar.value() + (self._pulse_dir * 5)
        if val >= 100:
            self._pulse_dir = -1
            val = 100
        elif val <= 0:
            self._pulse_dir = 1
            val = 0
        self.bar.setValue(val)

    def set_text(self, text: str):
        self.label.setText(text)

    def set_progress(self, val: int):
        self._pulse_timer.stop()
        self.bar.setValue(val)
