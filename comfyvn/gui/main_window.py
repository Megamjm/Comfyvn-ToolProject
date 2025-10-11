# comfyvn/gui/main_window.py
# 🎨 GUI Main Window (v1.1.2)
# Updated to integrate with ComfyVN Server Core 1.1.2
# [Code Updates Chat]

import sys, asyncio, json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import QTimer, Qt
import httpx

API_BASE = "http://127.0.0.1:8000"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
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

        # Connect buttons
        self.refresh_button.clicked.connect(lambda: asyncio.create_task(self.update_status()))
        self.pipeline_button.clicked.connect(lambda: asyncio.create_task(self.send_test_scene()))

        # Initial data
        asyncio.create_task(self.load_modes())
        asyncio.create_task(self.update_status())

        # Auto refresh
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: asyncio.create_task(self.update_status()))
        self.timer.start(10000)

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
    loop = asyncio.get_event_loop()
    window = MainWindow()
    window.show()
    loop.run_until_complete(asyncio.sleep(0))  # warm event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
# [ComfyVN: Code Updates Chat]
