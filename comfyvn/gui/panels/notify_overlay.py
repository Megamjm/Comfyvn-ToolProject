from PySide6.QtGui import QAction
# comfyvn/gui/panels/notify_overlay.py
# [COMFYVN Architect | v1.3 | this chat]
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PySide6.QtCore import Qt, QTimer

class NotifyOverlay(QWidget):
    """Transient overlay to show toasts in the corner."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(8,8,8,8)
        self.v.setSpacing(6)
        self.labels = []

    def toast(self, text: str, level: str = "info", ms: int = 3000):
        level = (level or "info").lower()
        accent = {
            "info": "#4da3ff",
            "success": "#4caf50",
            "warn": "#ffb300",
            "warning": "#ffb300",
            "error": "#ff5252",
        }.get(level, "#4da3ff")
        lab = QLabel(text)
        style = (
            "QLabel {{ background: rgba(30,30,30,220); color: white; border-radius:8px; padding:8px 12px;"
            " border-left: 4px solid {accent}; }}"
        ).format(accent=accent)
        lab.setStyleSheet(style)
        lab.setWordWrap(True)
        self.v.addWidget(lab, alignment=Qt.AlignRight)
        self.labels.append(lab)
        self._reposition()
        QTimer.singleShot(ms, lambda: self._remove(lab))

    def _remove(self, lab):
        self.v.removeWidget(lab)
        lab.setParent(None)
        if lab in self.labels: self.labels.remove(lab)
        self._reposition()

    def _reposition(self):
        if not self.parent(): return
        pr = self.parent().geometry()
        self.resize(pr.width(), pr.height())
        self.move(pr.x(), pr.y())

    def attach(self, main_window):
        self.setParent(main_window)
        self._reposition()
        self.show()
