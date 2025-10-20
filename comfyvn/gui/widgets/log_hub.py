from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/widgets/log_hub.py
import threading, time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel

class LogHub(QWidget):
    """Aggregates logs from ./logs/*.log and updates live."""
    def __init__(self, folder="logs", parent=None):
        super().__init__(parent)
        self.folder = Path(folder)
        self.folder.mkdir(exist_ok=True)
        v = QVBoxLayout(self)
        self.label = QLabel("System Log Stream"); self.label.setProperty("accent", True)
        v.addWidget(self.label)
        self.text = QTextEdit(); self.text.setReadOnly(True)
        v.addWidget(self.text,1)
        self.btn = QPushButton("Refresh Now")
        self.btn.clicked.connect(self.refresh); v.addWidget(self.btn)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)
        self.refresh()

    def refresh(self):
        content=[]
        for f in sorted(self.folder.glob("*.log")):
            try: content.append(f"[{f.name}]\n"+f.read_text(encoding='utf-8')[-2000:])
            except Exception: pass
        self.text.setPlainText("\n\n".join(content))