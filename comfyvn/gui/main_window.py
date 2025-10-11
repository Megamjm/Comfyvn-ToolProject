# comfyvn/gui/main_window.py
# 🎨 GUI Main Window (v1.1.3)
# Fixed: Async initialization (no running event loop)
# [Code Updates Chat]

import sys, asyncio, json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import QTimer
import httpx

API_BASE = "http://127.0.0.1:8000"

class MainWindow(QMainWindow):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop
        self.setWindowTitle("ComfyVN Control Panel")
        self.resize(640, 400)

        self.status_label = QLabel("Server status: Checking...")
        self.mode_box = QComboBox()
        self.refresh_button = QPushButton("Refresh Status")
        self.pipeline_button = QPushButton("Send Test Scene")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("Current Mode:"))
        layout.addWidget(self.mode_box)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.pipeline_button)
        layout.addWidget(QLabel("Logs:"))
        layout.addWidget(self.log_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Button bindings
        self.refresh_button.clicked.connect(lambda: self.run_async(self.update_status()))
        self.pipeline_button.clicked.connect(lambda: self.run_async(self.send_test_scene()))

        # Initialize GUI data
        self.run_async(self.load_modes())
        self.run_async(self.update_status())

        # Auto-refresh status every 10s
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: self.run_async(self.update_status()))
        self.timer.start(10000)

    def run_async(self, coro):
        """Safely schedule coroutine inside Qt via running loop."""
        asyncio.ensure_future(coro, loop=self.loop)

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
                data = r.json()
                modes = data.get("available_modes", [])
                self.mode_box.clear()
                self.mode_box.addItems(modes)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load modes: {e}")

    async def send_test_scene(self):
        test_scene = {
            "text": "[happy] The sun sets over the lake.",
            "characters": [{"name": "Caelum"}, {"name": "Luna"}],
            "background": "lake_evening"
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{API_BASE}/scene/pipeline", json=test_scene)
                res = r.json()
                self.log_view.append(f"Pipeline Response:\n{json.dumps(res, indent=2)}\n")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to send scene: {e}")

def main():
    app = QApplication(sys.argv)

    # Create dedicated asyncio loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    window = MainWindow(loop)
    window.show()

    # Integrate asyncio with Qt using QTimer
    def process_asyncio_events():
        loop.stop()
        loop.run_forever()

    timer = QTimer()
    timer.timeout.connect(process_asyncio_events)
    timer.start(10)

    # Run Qt event loop
    app.exec()

    # Cleanup asyncio loop
    loop.close()

if __name__ == "__main__":
    main()
# [Code Updates Chat]
