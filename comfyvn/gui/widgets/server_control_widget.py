# comfyvn/gui/widgets/server_control_widget.py
# 🧩 Server Control Widget — GUI Interface for Server State
# [ComfyVN_Architect | GUI Widgets v4.0 + Port Indicator]

import asyncio, time, threading, httpx, os
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QHBoxLayout,
    QFrame,
)
from comfyvn.gui.server_bridge import ServerBridge


class ServerControlWidget(QWidget):
    """Displays and controls server state with auto-poll, retry, and port indicator."""

    log_signal = Signal(str)
    status_signal = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bridge = ServerBridge()
        self._poll_interval = 3000
        self._last_launch = 0

        # --- Status labels ---
        self.status_label = QLabel("🔴 Server Offline")
        self.status_label.setStyleSheet("font-weight: bold;")

        self.port_label = QLabel("🧠 Port: —")
        self.port_label.setAlignment(Qt.AlignRight)
        self.port_label.setStyleSheet("color: #aaa; font-size: 10pt;")

        # combine status + port row
        row_info = QHBoxLayout()
        row_info.addWidget(self.status_label, 1)
        row_info.addWidget(self.port_label, 0)

        # --- Log area ---
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(180)

        # --- Buttons ---
        self.btn_launch = QPushButton("🚀 Launch Embedded Server")
        self.btn_launch.clicked.connect(self._launch_server)

        self.btn_refresh = QPushButton("🔄 Refresh Status")
        self.btn_refresh.clicked.connect(
            lambda: threading.Thread(target=self._check_status).start()
        )

        self.btn_open_diag = QPushButton("🧾 Open Diagnostics")
        self.btn_open_diag.clicked.connect(self._open_diagnostics)

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addLayout(row_info)
        layout.addWidget(self.log_view)

        row = QHBoxLayout()
        row.addWidget(self.btn_launch)
        row.addWidget(self.btn_refresh)
        row.addWidget(self.btn_open_diag)
        layout.addLayout(row)

        # --- Auto status timer ---
        self.timer = QTimer()
        self.timer.timeout.connect(
            lambda: threading.Thread(target=self._check_status).start()
        )
        self.timer.start(self._poll_interval)

        # --- Signals ---
        self.log_signal.connect(self._append_log)
        self.status_signal.connect(self._update_status_label)

        # initial check
        threading.Thread(target=self._check_status, daemon=True).start()

    # ------------------------------------------------------------
    # 🧭 Status
    # ------------------------------------------------------------
    def _check_status(self):
        """Query the current server health or status."""
        try:
            start = time.time()
            if not self.bridge.ensure_online():
                self.status_signal.emit(
                    {"ok": False, "message": "Server not reachable"}
                )
                return

            resp = self.bridge.get_status()
            resp["latency_ms"] = round((time.time() - start) * 1000, 1)
            self.status_signal.emit(resp)
        except Exception as e:
            self.status_signal.emit({"ok": False, "message": str(e)})

    @staticmethod
    def _open_diagnostics():
        diag_path = "./logs/diagnostics"
        if os.path.exists(diag_path):
            os.startfile(diag_path)
        else:
            print("[Diagnostics] Folder not found:", diag_path)

    # ------------------------------------------------------------
    # 🚀 Launch
    # ------------------------------------------------------------
    def _launch_server(self):
        now = time.time()
        if now - self._last_launch < 15:
            self._append_log("⚠️ Launch skipped — recently attempted.")
            return
        self._last_launch = now
        self._append_log("🛰 Starting embedded server thread …")

        t = threading.Thread(target=self.bridge.start_embedded_server, daemon=True)
        t.start()

    # ------------------------------------------------------------
    # 🧾 UI Updates
    # ------------------------------------------------------------
    def _append_log(self, text: str):
        self.log_view.append(text)

    def _update_status_label(self, data: dict):
        if not data.get("ok"):
            self.status_label.setText("🔴 Server Offline")
            self.port_label.setText("🧠 Port: —")
        else:
            latency = data.get("latency_ms", "?")
            ver = data.get("version", "?")
            port = self.bridge.api_base.split(":")[-1]
            src = "(Embedded)" if "127.0.0.1" in self.bridge.api_base else "(External)"
            self.status_label.setText(f"🟢 Online | v{ver} | {latency} ms")
            self.port_label.setText(f"🧠 Port: {port} {src}")
