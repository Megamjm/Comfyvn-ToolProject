from __future__ import annotations

from PySide6.QtGui import QAction

# comfyvn/gui/windows/extension_market_window.py
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from comfyvn.core.extension_store import refresh_catalog


class ExtensionMarketWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extensions Marketplace")
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Browse community extensions:"))
        self.list = QListWidget(self)
        self._populate()
        v.addWidget(self.list, 1)
        hb = QHBoxLayout()
        self.btn_install = QPushButton("Install (stub)")
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        hb.addWidget(self.btn_install)
        hb.addStretch(1)
        hb.addWidget(self.btn_close)
        v.addLayout(hb)

    def _populate(self) -> None:
        self.list.clear()
        for entry in refresh_catalog():
            trust = entry.trust.upper()
            label = f"[{trust}] {entry.name} — {entry.summary}"
            item = QListWidgetItem(label, self.list)
            item.setData(32, entry)  # Qt.UserRole
