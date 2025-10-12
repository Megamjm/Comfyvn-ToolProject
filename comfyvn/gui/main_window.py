# comfyvn/gui/main_window.py
# 🎨 ComfyVN Control Panel – v0.4-dev (Phase 3.4-A)
# Dynamic TopBarMenu + Status Framework + Advanced Task Manager + Server Core 1.1.4
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
from comfyvn.gui.widgets.progress_overlay import ProgressOverlay
from comfyvn.gui.widgets.dialog_helpers import info, error
from comfyvn.gui.server_bridge import ServerBridge
from comfyvn.gui.widgets.task_manager_dock import TaskManagerDock
from comfyvn.gui.components.advanced_task_manager_dock import AdvancedTaskManagerDock  # [GUI Code Production Chat]
from comfyvn.gui.widgets.topbar_menu import TopBarMenu
from comfyvn.gui.widgets.status_widget import StatusWidget
from comfyvn.core.system_monitor import SystemMonitor

try:
    from comfyvn.gui.world_ui import WorldUI
    HAS_WORLD_UI = True
except ImportError:
    HAS_WORLD_UI = False

API_BASE = os.getenv("COMFYVN_API", "http://127.0.0.1:8001")


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

        # Task-manager docks (classic + advanced)
        self.task_dock = TaskManagerDock(API_BASE, self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.task_dock)

        self.adv_task_dock = AdvancedTaskManagerDock(API_BASE, self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.adv_task_dock)
        self.adv_task_dock.hide()  # hidden by default; toggle from View menu

        # ----------------------------------------------------------
        # Tab structure
        # ----------------------------------------------------------
        self.main_tabs = QTabWidget()

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
        # Status bar (version + connection + indicators)
        # ----------------------------------------------------------
        self.version_label = QLabel("v0.4-dev")
        self.connection_label = QLabel("Server: Unknown")

        # Compact multi-source indicator row
        self.status_widget = StatusWidget(self)
        for name, tip in [
            ("server", "Server Core"),
            ("lmstudio", "LM Studio"),
            ("sillytavern", "SillyTavern"),
            ("world", "World Service"),
            ("cpu", "CPU Usage"),
            ("gpu", "GPU Usage"),
            ("ram", "RAM Usage"),
        ]:
            self.status_widget.add_indicator(name, tip)

        self.statusBar().addPermanentWidget(self.status_widget)
        self.statusBar().addPermanentWidget(self.version_label)
        self.statusBar().addPermanentWidget(self.connection_label)

        # ----------------------------------------------------------
        # Dynamic Top Bar Menu
        # ----------------------------------------------------------
        self.menu_bar = TopBarMenu(self)
        self.setMenuBar(self.menu_bar)

        # Default “View” submenu
        view_menu = self.menu_bar.addMenu("&View")
        act_toggle_tasks = view_menu.addAction("Toggle Task Manager")
        act_toggle_tasks.triggered.connect(
            lambda: self.task_dock.setVisible(not self.task_dock.isVisible())
        )
        act_toggle_adv = view_menu.addAction("Toggle Advanced Task Manager")
        act_toggle_adv.triggered.connect(
            lambda: self.adv_task_dock.setVisible(not self.adv_task_dock.isVisible())
        )

        # ----------------------------------------------------------
        # Event wiring
        # ----------------------------------------------------------
        self.refresh_button.clicked.connect(self._poll_server_status)
        self.pipeline_button.clicked.connect(lambda: self.run_async(self.send_test_scene()))

        # Server bridge + polling
        self.server_bridge = ServerBridge(API_BASE)
        self._init_status_polling()

        # ----------------------------------------------------------
        # System Monitor (Status Framework)
        # ----------------------------------------------------------
        self.monitor = SystemMonitor(API_BASE)
        self.monitor.on_update(self._on_monitor_update)
        self.monitor.start(interval=5)

    # --------------------------------------------------------------
    # Menu reloader (used by menu_system)
    # --------------------------------------------------------------
    def _reload_menus(self):
        """Reloads all menus dynamically."""
        self.menu_bar.clear()
        self.menu_bar.load_menus()

        # restore View submenu and custom toggles
        view_menu = self.menu_bar.addMenu("&View")
        act_toggle_tasks = view_menu.addAction("Toggle Task Manager")
        act_toggle_tasks.triggered.connect(
            lambda: self.task_dock.setVisible(not self.task_dock.isVisible())
        )
        act_toggle_adv = view_menu.addAction("Toggle Advanced Task Manager")
        act_toggle_adv.triggered.connect(
            lambda: self.adv_task_dock.setVisible(not self.adv_task_dock.isVisible())
        )

    # --------------------------------------------------------------
    # Utility helpers
    # --------------------------------------------------------------
    def run_async(self, coro):
        asyncio.ensure_future(coro, loop=self.loop)

    def _log(self, msg: str):
        self.log_view.append(msg)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    # --------------------------------------------------------------
    # Polling setup + handlers (ServerBridge)
    # --------------------------------------------------------------
    def _init_status_polling(self):
        """Start periodic server status polling via ServerBridge."""
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._poll_server_status)
        self.status_timer.start(5000)
        self._poll_server_status()  # initial check

    def _poll_server_status(self):
        """Fetch /status from Server Core."""
        def _cb(resp):
            if "mode" in resp:
                mode = resp.get("mode", "unknown")
                self.status_label.setText(f"Server: 🟢 Online | Mode: {mode}")
                self.connection_label.setText(f"Server: {mode} mode")
                self.connection_label.setStyleSheet("color: lime;")
                if self.mode_box.findText(mode) < 0:
                    self.mode_box.addItem(mode)
                    self.mode_box.setCurrentText(mode)
            else:
                self.status_label.setText("Server: 🔴 Offline")
                self.connection_label.setText("Server: Offline")
                self.connection_label.setStyleSheet("color: red;")
        self.server_bridge.get_status(_cb)

    # --------------------------------------------------------------
    # System Monitor callback → update indicators
    # --------------------------------------------------------------
    def _on_monitor_update(self, data: dict):
        # Connection sources
        srv = (data.get("server") or {}).get("state", "offline")
        lm = (data.get("lmstudio") or {}).get("state", "offline")
        st = (data.get("sillytavern") or {}).get("state", "offline")
        wd = (data.get("world") or {}).get("state", "offline")

        lm_model = (data.get("lmstudio") or {}).get("model", "unknown")
        self.status_widget.update_indicator("server", srv, f"Server Core: {srv}")
        self.status_widget.update_indicator("lmstudio", lm, f"LM Studio: {lm} (model: {lm_model})")
        self.status_widget.update_indicator("sillytavern", st, f"SillyTavern: {st}")
        self.status_widget.update_indicator("world", wd, f"World Service: {wd}")

        # Resources
        cpu = data.get("cpu_percent", 0)
        gpu = data.get("gpu_percent", 0)
        ram = data.get("ram_percent", 0)

        def load_to_state(v):
            if v >= 90:
                return "error"
            if v >= 70:
                return "busy"
            if v <= 5:
                return "idle"
            return "online"

        self.status_widget.update_indicator("cpu", load_to_state(cpu), f"CPU: {cpu:.0f}%")
        self.status_widget.update_indicator("gpu", load_to_state(gpu), f"GPU: {gpu:.0f}%")
        self.status_widget.update_indicator("ram", load_to_state(ram), f"RAM: {ram:.0f}%")

    # --------------------------------------------------------------
    # Async REST operations (demo trigger)
    # --------------------------------------------------------------
    async def send_test_scene(self):
        """Send a sample scene payload to /scene/render for testing."""
        scene = {
            "scene_id": "test_scene",
            "text": "[happy] The sun sets over the lake.",
            "characters": [{"name": "Caelum"}, {"name": "Luna"}],
            "background": "lake_evening"
        }
        self.overlay.set_text("Sending Test Scene …")
        self.overlay.start()
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{API_BASE}/scene/render", json=scene)
                res = r.json()
                self._log(f"Render Response:\n{json.dumps(res, indent=2)}")
                info(self, "Render Complete", "Test scene successfully sent to Server Core.")
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