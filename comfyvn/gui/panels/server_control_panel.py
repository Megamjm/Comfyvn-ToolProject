from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
# comfyvn/gui/panels/server_control_panel.py
# [ComfyVN Architect | Phase 2.05 | Soft Refresh + Async Bridge hook]
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from comfyvn.gui.services.server_bridge import ServerBridge


class ServerControlPanel(QFrame):
    def __init__(self):
        super().__init__(parent)
        self.bridge = ServerBridge()
        self.bridge.status_updated.connect(self._update)
        self._build_ui()
        self.bridge.start_polling()

    def _build_ui(self):
        lay = QHBoxLayout(self)
        self.lbl = QLabel("🔴 Server Offline")
        self.btn_refresh = QPushButton("Refresh Now")
        self.btn_refresh.clicked.connect(lambda: self.bridge.start_polling())
        lay.addWidget(self.lbl)
        lay.addStretch(1)
        lay.addWidget(self.btn_refresh)
        self.setLayout(lay)
        self.setFixedHeight(36)

    def _update(self, data: dict):
        if data.get("ok"):
            cpu = data.get("cpu", "?")
            mem = data.get("mem", "?")
            self.lbl.setText(f"🟢 Online | CPU {cpu}% | RAM {mem}%")
        else:
            self.lbl.setText("🔴 Server Offline")
