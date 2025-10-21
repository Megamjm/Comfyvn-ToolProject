from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)


class LogConsolePanel(QWidget):
    def __init__(self, log_dir="logs", files=("gui.log", "server.log")):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.files = [self.log_dir / f for f in files]

        v = QVBoxLayout(self)
        title = QLabel("Log Console")
        title.setStyleSheet("font-size:16px; font-weight:600;")
        v.addWidget(title)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        v.addWidget(self.view)

        row = QHBoxLayout()
        b_clear = QPushButton("Clear")
        b_clear.clicked.connect(self._clear)
        b_open = QPushButton("Open Folder")
        b_open.clicked.connect(self._open)
        row.addWidget(b_clear)
        row.addWidget(b_open)
        v.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setInterval(1200)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._poll()

    def _tail(self, path: Path, max_bytes=64000):
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - max_bytes))
                return f.read().decode(errors="replace")
        except Exception:
            return ""

    def _poll(self):
        out = []
        for p in self.files:
            out.append(f"--- {p.name} ---\n{self._tail(p)}\n")
        self.view.setPlainText("\n".join(out))
        self.view.moveCursor(self.view.textCursor().End)

    def _clear(self):
        for p in self.files:
            try:
                open(p, "w").close()
            except Exception:
                pass
        self._poll()

    def _open(self):
        QFileDialog.getOpenFileName(
            self, "Open Log", str(self.log_dir), "Log files (*.log);;All files (*.*)"
        )
