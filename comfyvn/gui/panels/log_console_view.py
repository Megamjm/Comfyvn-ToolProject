from PySide6.QtGui import QAction
# comfyvn/gui/panels/log_console_view.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QTextEdit
from comfyvn.core.notifier import notifier

class LogConsoleView(QDockWidget):
    def __init__(self):
        super().__init__("Log Console")
        c = QWidget(); lay = QVBoxLayout(c)
        self.txt = QTextEdit(); self.txt.setReadOnly(True)
        lay.addWidget(self.txt); self.setWidget(c)
        self._drain()

    def _drain(self):
        for evt in notifier.list():
            self.txt.append(f"[{evt['level']}] {evt['msg']}")