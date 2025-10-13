# comfyvn/gui/main_window.py
# 🎨 ComfyVN Control Panel — v0.4-dev (Phase 3.9 Debug + Auto Server)
# Combines: Server Control, Playground, Task Management, and System Dashboard
# [ComfyVN Architect | Main GUI Integration Layer]

from __future__ import annotations
import os, sys, asyncio, json, webbrowser, httpx, threading, time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QTabWidget,
    QMessageBox,
)
from PySide6.QtGui import QAction

# --- Internal imports ---
from comfyvn.gui.settings_ui import SettingsUI
from comfyvn.gui.asset_browser import AssetBrowser
from comfyvn.gui.playground_ui import PlaygroundUI
from comfyvn.gui.widgets.progress_overlay import ProgressOverlay
from comfyvn.gui.widgets.dialog_helpers import info, error
from comfyvn.gui.server_bridge import ServerBridge
from comfyvn.gui.widgets.task_manager_dock import TaskManagerDock
from comfyvn.gui.widgets.topbar_menu import TopBarMenu
from comfyvn.gui.widgets.status_widget import StatusWidget
from comfyvn.core.system_monitor import SystemMonitor
from comfyvn.gui.roleplay_import_ui import RoleplayImportUI
from comfyvn.gui.roleplay_preview_ui import RoleplayPreviewUI
from comfyvn.gui.lora_manager_ui import LoRAManagerUI
from comfyvn.gui.playground_hub import PlaygroundHub
from comfyvn.gui.widgets.server_control_widget import ServerControlWidget

try:
    from comfyvn.gui.widgets.advanced_task_manager_dock import AdvancedTaskManagerDock

    HAS_ADV_DOCK = True
except Exception:
    HAS_ADV_DOCK = False

API_BASE = os.getenv("COMFYVN_API", "http://127.0.0.1:8001")


# -------------------------------------------------------------------------
# Utility: Embedded server launcher
# -------------------------------------------------------------------------
def try_launch_embedded_server():
    """Try to launch the embedded ComfyVN server if offline."""
    try:
        from comfyvn.app import launch_server_thread

        print(
            "[ComfyVN GUI] 🛰  Attempting to launch embedded server on 127.0.0.1:8001 …"
        )
        t = launch_server_thread("127.0.0.1", 8001)
        time.sleep(1)
        print("[ComfyVN GUI] ✅ Embedded server thread started:", t)
        return True
    except Exception as e:
        print("[ComfyVN GUI] ⚠️  Embedded server launch failed:", e)
        return False


# =====================================================================
# 🧩 Main Window
# =====================================================================
class MainWindow(QMainWindow):
    """Main ComfyVN Control Panel"""

    server_status_received = Signal(dict)
    server_status_failed = Signal(str)
    log_message = Signal(str)
    job_event = Signal(dict)
    task_update = Signal(dict)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop
        self.setWindowTitle("ComfyVN Control Panel — v3.9")
        self.resize(1380, 860)
        print("[ComfyVN GUI] 🚀 Initializing main window …")

        # ---------------------------------------------------------------
        # Tabs and Layout
        # ---------------------------------------------------------------
        self.main_tabs = QTabWidget()
        self.server_control_tab = ServerControlWidget(self)
        self.assets_tab = AssetBrowser()
        self.playground_tab = PlaygroundUI()
        self.role_import_tab = RoleplayImportUI(self)
        self.role_preview_tab = RoleplayPreviewUI(self)
        self.lora_tab = LoRAManagerUI(task_manager=None)
        self.settings_tab = SettingsUI()

        for w, name in [
            (self.server_control_tab, "System Control"),
            (self.assets_tab, "Asset Browser"),
            (self.playground_tab, "Playground"),
            (self.role_import_tab, "Roleplay Import"),
            (self.role_preview_tab, "Roleplay Preview"),
            (self.lora_tab, "LoRA Manager"),
            (self.settings_tab, "Settings"),
        ]:
            self.main_tabs.addTab(w, name)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.main_tabs)
        self.setCentralWidget(container)

        # ---------------------------------------------------------------
        # Task Manager Dock(s)
        # ---------------------------------------------------------------
        print("[ComfyVN GUI] 🧩 Initializing TaskManagerDock …")
        self.task_dock = TaskManagerDock(API_BASE, self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.task_dock)

        if HAS_ADV_DOCK:
            self.adv_task_dock = AdvancedTaskManagerDock(API_BASE, self)
            self.addDockWidget(Qt.RightDockWidgetArea, self.adv_task_dock)
            self.adv_task_dock.hide()

        self.job_event.connect(self.task_dock.handle_event)
        self.task_update.connect(self.task_dock.handle_update)

        # ---------------------------------------------------------------
        # Status bar
        # ---------------------------------------------------------------
        self.status_widget = StatusWidget(self)
        for key in ["server", "lmstudio", "sillytavern", "world", "cpu", "gpu", "ram"]:
            self.status_widget.add_indicator(key, key)
        self.statusBar().addPermanentWidget(self.status_widget)
        self.statusBar().addPermanentWidget(QLabel("v3.9"))

        # ---------------------------------------------------------------
        # Backend Bridge + Monitor
        # ---------------------------------------------------------------
        self.server_bridge = ServerBridge(API_BASE)
        self.monitor = SystemMonitor(API_BASE)
        self.monitor.on_update(self._on_monitor_update)
        self.monitor.start(interval=5)

        # ===============================================================
        # 🧩 Menus — Unified Top Bar
        # ===============================================================
        self.menu_bar = TopBarMenu(self)
        self.setMenuBar(self.menu_bar)  # ✅ Attach it to QMainWindow

        # ---------------------------------------------------------------
        # Signals
        # ---------------------------------------------------------------
        self.server_status_received.connect(self._on_server_status)
        self.server_status_failed.connect(self._on_server_status_error)
        print("[ComfyVN GUI] ✅ Initialization complete.")

        # ---------------------------------------------------------------
        # Start polling
        # ---------------------------------------------------------------
        self._playground_hub = None
        self._init_status_polling()

    # ==================================================================
    # 🔄 Polling + Server Detection
    # ==================================================================
    def _init_status_polling(self):
        print("[ComfyVN GUI] 🩺 Starting server polling …")
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_server_status)
        self._status_timer.start(6000)
        self._poll_server_status()

    def _poll_server_status(self):
        async def _async_poll():
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(f"{API_BASE}/status")
                    if r.status_code != 200:
                        raise Exception(f"HTTP {r.status_code}")
                    data = r.json()
                    self.server_status_received.emit(data)
            except Exception as e:
                print(f"[ComfyVN GUI] ⚠️  Server unreachable: {e}")
                self.server_status_failed.emit(str(e))

        asyncio.ensure_future(_async_poll(), loop=self.loop)

    def _on_server_status(self, resp: dict):
        mode = resp.get("mode", "unknown")
        version = resp.get("version", "?")
        print(f"[ComfyVN GUI] 🟢 Server online — v{version}, mode={mode}")
        self.status_widget.update_indicator("server", "online", f"Server v{version}")

    def _on_server_status_error(self, err: str):
        print(f"[ComfyVN GUI] 🔴 Server offline ({err}) — retrying …")
        # attempt to auto-launch embedded server
        launched = try_launch_embedded_server()
        if not launched:
            print(
                "[ComfyVN GUI] ❌ Auto-launch failed. Waiting for manual server start."
            )
        self.status_widget.update_indicator("server", "error", f"Offline: {err}")

    # ==================================================================
    # Monitor Updates
    # ==================================================================
    def _on_monitor_update(self, data: dict):
        cpu = data.get("cpu_percent", 0)
        self.status_widget.update_indicator("cpu", "online", f"CPU {cpu:.0f}%")

    # ==================================================================
    # Playground Hub
    # ==================================================================
    def open_playground_hub(self):
        print("[ComfyVN GUI] 🧩 Opening Playground Hub …")
        if not self._playground_hub:
            self._playground_hub = PlaygroundHub(self)
        self._playground_hub.show()
        self._playground_hub.raise_()
        self._playground_hub.activateWindow()

    # ==================================================================
    # Cleanup
    # ==================================================================
    def closeEvent(self, e):
        print("[ComfyVN GUI] 🧹 Cleaning up …")
        try:
            if hasattr(self, "_status_timer"):
                self._status_timer.stop()
            if hasattr(self, "task_dock") and hasattr(self.task_dock, "worker"):
                self.task_dock.worker.stop()
                self.task_dock.worker.wait(1500)
        finally:
            print("[ComfyVN GUI] 💨 Closed cleanly.")
            super().closeEvent(e)


# =====================================================================
# 🚀 Entry point
# =====================================================================
def main():
    print("[ComfyVN GUI] 🖥️ Starting ComfyVN Control Panel …")
    if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication(sys.argv)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    window = MainWindow(loop)
    window.show()

    def pump_loop():
        loop.call_soon(loop.stop)
        loop.run_forever()

    timer = QTimer()
    timer.timeout.connect(pump_loop)
    timer.start(10)
    app.exec()
    loop.close()


if __name__ == "__main__":
    main()

    # ==================================================================
    # 📁 Placeholder project actions (for File menu)
    # ==================================================================
    def new_project(self):
        print("[MainWindow] 🆕 New Project (stub)")

    def open_project(self):
        print("[MainWindow] 📂 Open Project (stub)")

    def open_project_path(self, path):
        print(f"[MainWindow] 📂 Open Recent Project: {path}")

    def save_snapshot(self):
        print("[MainWindow] 💾 Save Snapshot (stub)")

    def restore_snapshot(self):
        print("[MainWindow] ♻️ Restore Snapshot (stub)")
