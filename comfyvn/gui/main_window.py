# comfyvn/gui/main_window.py
# 🎨 ComfyVN Control Panel – v1.1.4
# Integrates with Server Core 1.1.4
# [Code Updates Chat]

import os, sys, asyncio, json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QMessageBox, QTabWidget
)
from PySide6.QtCore import QTimer, Qt
import httpx

from comfyvn.gui.asset_browser import AssetBrowser   # 👈 ensure exists

API_BASE = os.getenv("COMFYVN_API", "http://127.0.0.1:8000")
self.assets_tab = AssetBrowser(loop, API_BASE)
main_tabs.addTab(control_tab, "Server Control")
main_tabs.addTab(self.assets_tab, "Asset Browser")

class MainWindow(QMainWindow):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop
        self.setWindowTitle("ComfyVN Control Panel")
        self.resize(960, 600)

        # --- Core UI Elements ---
        self.status_label = QLabel("Server status: Checking...")
        self.mode_box = QComboBox()
        self.refresh_button = QPushButton("Refresh Status")
        self.pipeline_button = QPushButton("Send Test Scene")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        # --- Layout ---
        main_tabs = QTabWidget()
        control_tab = QWidget()
        vbox = QVBoxLayout(control_tab)
        vbox.addWidget(self.status_label)
        vbox.addWidget(QLabel("Current Mode:"))
        vbox.addWidget(self.mode_box)
        vbox.addWidget(self.refresh_button)
        vbox.addWidget(self.pipeline_button)
        vbox.addWidget(QLabel("Logs:"))
        vbox.addWidget(self.log_view)
        vbox.addStretch()

        self.assets_tab = AssetBrowser(loop, API_BASE)
        main_tabs.addTab(control_tab, "Server Control")
        main_tabs.addTab(self.assets_tab, "Asset Browser")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(main_tabs)
        self.setCentralWidget(container)

        # --- Events ---
        self.refresh_button.clicked.connect(lambda: self.run_async(self.update_status()))
        self.pipeline_button.clicked.connect(lambda: self.run_async(self.send_test_scene()))

        # --- Initialization ---
        self.run_async(self.load_modes())
        self.run_async(self.update_status())

        # --- Auto-refresh ---
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: self.run_async(self.update_status()))
        self.timer.start(10000)

    def run_async(self, coro):
        asyncio.ensure_future(coro, loop=self.loop)

    # ------------------------------------------------------------------
    # Async API methods
    # ------------------------------------------------------------------
    async def update_status(self):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{API_BASE}/gui/state")
                data = r.json()
                online = data.get("status") == "online"
                self.status_label.setText(
                    f"Server status: {'🟢 Online' if online else '🔴 Offline'} | Mode: {data.get('mode')}"
                )
        except Exception as e:
            self.status_label.setText(f"Error contacting server: {e}")

    async def load_modes(self):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{API_BASE}/mode/list")
                modes = r.json().get("available_modes", [])
                self.mode_box.clear()
                self.mode_box.addItems(modes)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load modes: {e}")

    async def send_test_scene(self):
        scene = {
            "text": "[happy] The sun sets over the lake.",
            "characters": [{"name": "Caelum"}, {"name": "Luna"}],
            "background": "lake_evening"
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{API_BASE}/scene/pipeline", json=scene)
                res = r.json()
                self.log_view.append(f"Pipeline Response:\n{json.dumps(res, indent=2)}\n")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to send scene: {e}")

# ----------------------------------------------------------------------
# Application Entry
# ----------------------------------------------------------------------
def main():
    # detect headless mode
    if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication(sys.argv)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    window = MainWindow(loop)
    window.show()

    # Integrate asyncio + Qt
    def pump_loop():
        loop.stop()
        loop.run_forever()

    timer = QTimer()
    timer.timeout.connect(pump_loop)
    timer.start(10)

    app.exec()
    loop.close()


if __name__ == "__main__":
    main()
# [ComfyVN GUI v1.1.4]
