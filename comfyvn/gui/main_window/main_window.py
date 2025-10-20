# -------------------------------------------------------------
# 🎛️ ComfyVN Studio Main Window — modular, dynamic, efficient
# -------------------------------------------------------------
from __future__ import annotations
import sys, subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QDockWidget, QWidget, QVBoxLayout, QLabel, QStatusBar
)
from PySide6.QtGui import QAction

# Core studio shell & mixins
from .shell_studio import ShellStudio
from .quick_access_toolbar import QuickAccessToolbarMixin
from comfyvn.gui.core.dock_manager import DockManager
from comfyvn.gui.core.workspace_controller import WorkspaceController

# Dynamic systems
from comfyvn.core.menu_runtime_bridge import menu_registry, reload_from_extensions
from comfyvn.core.shortcut_registry import shortcut_registry, load_shortcuts_from_folder

# Services
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.core.theme_manager import apply_theme

# Panels (lazy-instantiated)
from comfyvn.gui.panels.studio_center import StudioCenter
from comfyvn.gui.panels.asset_browser import AssetBrowser
from comfyvn.gui.panels.playground_panel import PlaygroundPanel
from comfyvn.gui.panels.timeline_panel import TimelinePanel
from comfyvn.gui.panels.telemetry_panel import TelemetryPanel
from comfyvn.gui.widgets.log_hub import LogHub

# Central space
from comfyvn.gui.panels.central_space import CentralSpace

# Menus
from comfyvn.gui.main_window.menu_bar import ensure_menu_bar, update_window_menu_state, rebuild_menus_from_registry

def _detached_server():
    """Launch the backend as a detached process; return Popen or None."""
    try:
        exe = sys.executable
        script = Path("comfyvn/server/app.py").resolve()
        log_path = Path("logs/server_detached.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as log:
            proc = subprocess.Popen([exe, str(script)], stdout=log, stderr=log)
        print(f"[ComfyVN GUI] 🚀 Detached server started (PID={proc.pid})")
        return proc
    except Exception as e:
        print(f"[ComfyVN GUI] ❌ Failed to launch detached server: {e}")
        return None

class MainWindow(ShellStudio, QuickAccessToolbarMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyVN Studio")
        self.resize(1280, 800)

        # Services & controllers
        self.bridge = ServerBridge(base="http://127.0.0.1:8001")
        self.dockman = DockManager(self)
        self.workspace = WorkspaceController(self)

        # Central canvas (assets & editors dock around it)
        self.central = CentralSpace(
            open_assets=self.open_asset_browser,
            open_timeline=self.open_timeline,
            open_logs=self.open_log_hub,
        )
        self.setCentralWidget(self.central)

        # Status bar (bottom, best practice) with server status
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_label = QLabel("🔴 Server: Unknown")
        self._status.addPermanentWidget(self._status_label, 1)

        # Toolbars (Quick Access) are dynamic via shortcut registry
        self._rebuild_shortcuts_toolbar()

        # Menus are dynamic via extension folder
        ensure_menu_bar(self)
        self.reload_menus()

        # Background server: start if not reachable
        QTimer.singleShot(400, self._ensure_server_online)
        # Periodic server heartbeat to status bar
        self._heartbeat = QTimer(self); self._heartbeat.timeout.connect(self._poll_server_status); self._heartbeat.start(2000)

    # --------------------
    # Dynamic systems
    # --------------------
    def reload_menus(self):
        """Reload menus from the on-disk extensions folder -> menu registry -> menubar."""
        try:
            reload_from_extensions(menu_registry, base_folder=Path("extensions"))
        except Exception as e:
            print("[Menu] reload error:", e)
        rebuild_menus_from_registry(self, menu_registry)

    def _rebuild_shortcuts_toolbar(self):
        """Rebuild Quick Access toolbar from shortcuts folder."""
        try:
            load_shortcuts_from_folder(shortcut_registry, Path("shortcuts"))
        except Exception as e:
            print("[Shortcuts] load error:", e)
        # QuickAccessToolbarMixin expects items on self via registry
        self.build_quick_access_toolbar(shortcut_registry.iter_actions())

    # --------------------
    # Panel openers (lazy)
    # --------------------
    def open_studio_center(self):
        if not hasattr(self, "_studio_center"):
            self._studio_center = StudioCenter(self.bridge, self)
            self.dockman.dock(self._studio_center, "Studio Center")
        self._studio_center.setVisible(True)

    def open_asset_browser(self):
        if not hasattr(self, "_asset_browser"):
            self._asset_browser = AssetBrowser(self.bridge, self)
            self.dockman.dock(self._asset_browser, "Assets")
        self._asset_browser.setVisible(True)

    def open_playground(self):
        if not hasattr(self, "_playground"):
            self._playground = PlaygroundPanel(self.bridge, self)
            self.dockman.dock(self._playground, "Playground")
        self._playground.setVisible(True)

    def open_timeline(self):
        if not hasattr(self, "_timeline"):
            self._timeline = TimelinePanel(self.bridge, self)
            self.dockman.dock(self._timeline, "Timeline")
        self._timeline.setVisible(True)

    def open_telemetry(self):
        if not hasattr(self, "_telemetry"):
            self._telemetry = TelemetryPanel(self.bridge, self)
            self.dockman.dock(self._telemetry, "System Status")
        self._telemetry.setVisible(True)

    def open_log_hub(self):
        if not hasattr(self, "_loghub"):
            self._loghub = LogHub()
            self.dockman.dock(self._loghub, "Log Hub")
        self._loghub.setVisible(True)

    # --------------------
    # Server monitoring
    # --------------------
    def _ensure_server_online(self):
        try:
            ok = self.bridge.ping()
            if not ok:
                _detached_server()
        except Exception:
            _detached_server()

    def _poll_server_status(self):
        try:
            # Expect system_api prefix "/system"
            s = self.bridge.get_json("/system/status") or {}
            healthy = bool(s.get("ok") or s.get("healthy"))
            self._status_label.setText(("🟢" if healthy else "🟠") + " Server: " + ("OK" if healthy else "Degraded"))
        except Exception:
            self._status_label.setText("🔴 Server: Offline")


def main():
    app = QApplication(sys.argv)
    try:
        apply_theme(app, 'default_dark')
    except Exception:
        pass
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
