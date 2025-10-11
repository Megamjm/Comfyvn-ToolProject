# comfyvn/gui/main_window.py
# 🎨 ComfyVN Control Panel – v1.1.5-dev
# Integrates Server Core 1.1.4 and GUI v0.3 Components
# [🎨 GUI Code Production Chat]

import os, sys, asyncio, json, httpx
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QTextEdit, QComboBox, QPushButton, QMessageBox, QTabWidget
)
from PySide6.QtCore import QTimer, Qt

# --- Internal GUI imports ---
from comfyvn.gui.settings_ui import SettingsUI
from comfyvn.gui.asset_browser import AssetBrowser
from comfyvn.gui.playground_ui import PlaygroundUI
from comfyvn.gui.components.progress_overlay import ProgressOverlay
from comfyvn.gui.components.dialog_helpers import info, error
from comfyvn.gui.server_bridge import ServerBridge
from comfyvn.gui.components.task_manager_dock import TaskManagerDock

# Optional world-UI support
try:
    from comfyvn.gui.world_ui import WorldUI
    HAS_WORLD_UI = True
except ImportError:
    HAS_WORLD_UI = False

API_BASE = os.getenv("COMFYVN_API", "http://127.0.0.1:8000")


class MainWindow(QMainWindow):
    """Main control interface for ComfyVN."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop
        self.setWindowTitle("ComfyVN Control Panel")
        self.resize(1280, 800)

        # ----------------------------------------------------------
        # Core widgets
        # ----------------------------------------------------------
        self.status_label = QLabel("Server status: Checking …")
        self.mode_box = QComboBox()
        self.refresh_button = QPushButton("Refresh Status")
        self.pipeline_button = QPushButton("Send Test Scene")
        self.log_view = QTextEdit(readOnly=True)

        # Overlay for async tasks
        self.overlay = ProgressOverlay(self, "Connecting to Server …", cancellable=False)
        self.overlay.hide()

        # Task-manager dock
        self.task_dock = TaskManagerDock(API_BASE, self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.task_dock)

        # ----------------------------------------------------------
        # Tab structure
        # ----------------------------------------------------------
        self.main_tabs = QTabWidget()

        # Control tab
        self.control_tab = QWidget()
        vbox = QVBoxLayout(self.control_tab)
        vbox.addWidget(self.status_label)
        vbox.addWidget(QLabel("Current Mode:"))
        vbox.addWidget(self.mode_box)
        vbox.addWidget(self.refresh_button)
        vbox.addWidget(self.pipeline_button)
        vbox.addWidget(QLabel("Logs:"))
        vbox.addWidget(self.log_view)
        vbox.addStretch()

        # Other tabs
        self.settings_tab = SettingsUI()
        self.assets_tab = AssetBrowser()
        self.playground_tab = PlaygroundUI()

        self.main_tabs.addTab(self.control_tab, "Server Control")
        self.main_tabs.addTab(self.assets_tab, "Asset Browser")
        self.main_tabs.addTab(self.settings_tab, "Settings")
        self.main_tabs.addTab(self.playground_tab, "Playground")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.main_tabs)
        self.setCentralWidget(container)

        # ----------------------------------------------------------
        # Status-bar labels
        # ----------------------------------------------------------
        self.version_label = QLabel("v1.1.5-dev")
        self.connection_label = QLabel("Server: Unknown")
        self.statusBar().addPermanentWidget(self.version_label)
        self.statusBar().addPermanentWidget(self.connection_label)

        # ----------------------------------------------------------
        # Menu bar
        # ----------------------------------------------------------
        self._build_menu()
        view_menu = self.menuBar().addMenu("&View")
        act_toggle_tasks = view_menu.addAction("Toggle Task Manager")
        act_toggle_tasks.triggered.connect(
            lambda: self.task_dock.setVisible(not self.task_dock.isVisible())
        )

        # ----------------------------------------------------------
        # Event wiring
        # ----------------------------------------------------------
        self.refresh_button.clicked.connect(lambda: self.run_async(self.update_status()))
        self.pipeline_button.clicked.connect(lambda: self.run_async(self.send_test_scene()))

        # Server bridge
        self.server_bridge = ServerBridge(API_BASE)
        self.run_async(self.load_modes())
        self.run_async(self.update_status())

        # Auto-refresh every 10 s
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: self.run_async(self.update_status()))
        self.timer.start(10000)

    # --------------------------------------------------------------
    # Menu creation
    # --------------------------------------------------------------
    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        act_quit = file_menu.addAction("Quit")
        act_quit.triggered.connect(self.close)

        tools_menu = menubar.addMenu("&Tools")
        act_test_server = tools_menu.addAction("Test Server")
        act_test_server.triggered.connect(lambda: self.server_bridge.test_connection(self._log))
        act_refresh = tools_menu.addAction("Refresh Now")
        act_refresh.triggered.connect(lambda: self.run_async(self.update_status()))

        if HAS_WORLD_UI:
            settings_menu = menubar.addMenu("&Settings")
            world_action = settings_menu.addAction("World Manager")
            world_action.triggered.connect(lambda: WorldUI().show())

    # --------------------------------------------------------------
    # Utility helpers
    # --------------------------------------------------------------
    def run_async(self, coro):
        asyncio.ensure_future(coro, loop=self.loop)

    def _log(self, msg: str):
        self.log_view.append(msg)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    # --------------------------------------------------------------
    # Async REST operations
    # --------------------------------------------------------------
    async def update_status(self):
        """Poll Server Core state."""
        self.overlay.set_text("Updating status …")
        self.overlay.start()
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{API_BASE}/gui/state")
                data = r.json()
                online = data.get("status") == "online"
                mode = data.get("mode", "Unknown")
                self.status_label.setText(
                    f"Server status: {'🟢 Online' if online else '🔴 Offline'} | Mode: {mode}"
                )
                self.connection_label.setText("Server: Connected" if online else "Server: Offline")
                self._log(f"Server response: {data}")
        except Exception as e:
            self.status_label.setText(f"Error contacting server: {e}")
            self.connection_label.setText("Server: Error")
            self._log(f"[Error] update_status: {e}")
        finally:
            self.overlay.stop()

    async def load_modes(self):
        """Fetch available modes from Server Core."""
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{API_BASE}/mode/list")
                modes = r.json().get("available_modes", [])
                self.mode_box.clear()
                self.mode_box.addItems(modes)
                self._log(f"Loaded modes: {modes}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load modes: {e}")
            self._log(f"[Error] load_modes: {e}")

    async def send_test_scene(self):
        """Send sample scene payload to Server Core pipeline."""
        scene = {
            "text": "[happy] The sun sets over the lake.",
            "characters": [{"name": "Caelum"}, {"name": "Luna"}],
            "background": "lake_evening"
        }
        self.overlay.set_text("Sending Test Scene …")
        self.overlay.start()
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{API_BASE}/scene/pipeline", json=scene)
                res = r.json()
                self._log(f"Pipeline Response:\n{json.dumps(res, indent=2)}")
                info(self, "Pipeline Complete", "Test scene successfully sent to Server Core.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to send scene: {e}")
            self._log(f"[Error] send_test_scene: {e}")
        finally:
            self.overlay.stop()


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
def main():
    if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication(sys.argv)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    window = MainWindow(loop)
    window.show()

    # integrate asyncio loop with Qt
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
