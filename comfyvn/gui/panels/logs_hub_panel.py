from __future__ import annotations

# comfyvn/gui/panels/logs_hub_panel.py
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)


class _TailView(QPlainTextEdit):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self._path = path
        self._pos = 0
        self._follow = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1500)

    def _tick(self):
        try:
            if not self._path.exists():
                return
            with self._path.open("rb") as f:
                f.seek(self._pos)
                chunk = f.read(64 * 1024)
                if chunk:
                    self._pos = f.tell()
                    self.moveCursor(Qt.TextCursorEnd)
                    try:
                        self.insertPlainText(chunk.decode("utf-8", errors="ignore"))
                    except Exception:
                        pass
                    if self._follow:
                        self.verticalScrollBar().setValue(
                            self.verticalScrollBar().maximum()
                        )
        except Exception:
            pass

    def toggle_follow(self):
        self._follow = not self._follow


class LogsHubPanel(QWidget):
    """Tabbed live-tail across common log files."""

    def __init__(self, log_dir: Path = Path("logs"), parent=None):
        super().__init__(parent)
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        tabs = QTabWidget(self)
        rows = QVBoxLayout(self)
        rows.setContentsMargins(6, 6, 6, 6)
        rows.addWidget(tabs)

        toolbar = QHBoxLayout()
        btn_follow = QPushButton("Toggle Follow")
        btn_open = QPushButton("Open Logs Folder")
        toolbar.addWidget(btn_follow)
        toolbar.addStretch(1)
        toolbar.addWidget(btn_open)
        rows.addLayout(toolbar)

        files = [
            ("GUI", self.log_dir / "gui.log"),
            ("Server", self.log_dir / "server.log"),
            ("Render", self.log_dir / "render.log"),
            ("Advisory", self.log_dir / "advisory.log"),
            ("Combined", self.log_dir / "combined.log"),
        ]
        self._tails: List[_TailView] = []
        for title, path in files:
            tv = _TailView(path)
            self._tails.append(tv)
            tabs.addTab(tv, title)

        btn_follow.clicked.connect(self._toggle_follow_all)
        btn_open.clicked.connect(self._open_dir)

    def _toggle_follow_all(self):
        for tv in self._tails:
            tv.toggle_follow()

    def _open_dir(self):
        try:
            import os
            import platform
            import subprocess

            d = str(self.log_dir.resolve())
            if platform.system() == "Windows":
                os.startfile(d)  # type: ignore
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception:
            pass
