from __future__ import annotations

from PySide6.QtGui import QAction
# comfyvn/gui/windows/extension_market_window.py
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget,
                               QPushButton, QVBoxLayout)

from comfyvn.core.extension_store import CATALOG


class ExtensionMarketWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extensions Marketplace (stub)")
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Browse community extensions (stub):"))
        self.list = QListWidget(self)
        for item in CATALOG:
            self.list.addItem(f"{item.name} — {item.desc}")
        v.addWidget(self.list, 1)
        hb = QHBoxLayout()
        self.btn_install = QPushButton("Install (stub)")
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        hb.addWidget(self.btn_install)
        hb.addStretch(1)
        hb.addWidget(self.btn_close)
        v.addLayout(hb)
