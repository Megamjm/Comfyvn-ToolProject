# -------------------------------------------------------------
# 🎛️ ComfyVN Studio Main Window — modular, dynamic, efficient
# -------------------------------------------------------------
from __future__ import annotations
import logging
import sys, subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QDockWidget, QWidget, QVBoxLayout, QLabel, QStatusBar
)
from PySide6.QtGui import QAction, QDesktopServices

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
from comfyvn.gui.panels.settings_panel import SettingsPanel
from comfyvn.gui.widgets.log_hub import LogHub

# Central space
from comfyvn.gui.panels.central_space import CentralSpace

# Menus
from comfyvn.gui.main_window.menu_bar import ensure_menu_bar, update_window_menu_state, rebuild_menus_from_registry
from comfyvn.gui.main_window.menu_defaults import register_core_menu_items

logger = logging.getLogger(__name__)

def _detached_server():
    """Launch the backend as a detached process; return Popen or None."""
    try:
        exe = sys.executable
        script = Path("comfyvn/app.py").resolve()
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
        workspace_store = Path("data/workspaces")
        self.workspace = WorkspaceController(self, workspace_store)

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
            menu_registry.clear()
            register_core_menu_items(menu_registry)
            reload_from_extensions(menu_registry, base_folder=Path("extensions"), clear=False)
        except Exception as e:
            print("[Menu] reload error:", e)
            logger.exception("Menu reload failed: %s", e)
        rebuild_menus_from_registry(self, menu_registry)
        logger.debug("Menus rebuilt with %d items", len(menu_registry.items))

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
        dock = getattr(self, "_studio_center_dock", None)
        if dock is None:
            panel = StudioCenter(self.bridge, self)
            dock = self.dockman.dock(panel, "Studio Center")
            self._studio_center_dock = dock
            logger.debug("Studio Center module created")
        dock.setVisible(True)
        dock.raise_()

    def open_asset_browser(self):
        dock = getattr(self, "_asset_browser", None)
        if dock is None:
            dock = AssetBrowser("data/assets")
            self.dockman.dock(dock, "Assets")
            self._asset_browser = dock
            logger.debug("Asset Browser module created")
        dock.setVisible(True)
        dock.raise_()

    def open_playground(self):
        dock = getattr(self, "_playground", None)
        if dock is None:
            dock = PlaygroundPanel(self.bridge.base)
            self.dockman.dock(dock, "Playground")
            self._playground = dock
            logger.debug("Playground module created")
        dock.setVisible(True)
        dock.raise_()

    def open_timeline(self):
        dock = getattr(self, "_timeline", None)
        if dock is None:
            dock = TimelinePanel()
            self.dockman.dock(dock, "Timeline")
            self._timeline = dock
            logger.debug("Timeline module created")
        dock.setVisible(True)
        dock.raise_()

    def open_telemetry(self):
        dock = getattr(self, "_telemetry_dock", None)
        if dock is None:
            panel = TelemetryPanel(self.bridge.base)
            dock = self.dockman.dock(panel, "System Status")
            self._telemetry_dock = dock
            logger.debug("Telemetry module created")
        dock.setVisible(True)
        dock.raise_()

    def open_log_hub(self):
        dock = getattr(self, "_loghub_dock", None)
        if dock is None:
            panel = LogHub()
            dock = self.dockman.dock(panel, "Log Hub")
            self._loghub_dock = dock
            logger.debug("Log Hub module created")
        dock.setVisible(True)
        dock.raise_()

    def open_settings_panel(self):
        dock = getattr(self, "_settings_panel", None)
        if dock is None:
            dock = SettingsPanel(self.bridge)
            self.dockman.dock(dock, "Settings")
            self._settings_panel = dock
            logger.debug("Settings module created")
        dock.setVisible(True)
        dock.raise_()

    # --------------------
    # Utility helpers
    # --------------------
    def launch_detached_server(self):
        _detached_server()

    def open_projects_folder(self):
        self._open_folder(Path("data/projects"))

    def open_data_folder(self):
        self._open_folder(Path("data"))

    def open_logs_folder(self):
        self._open_folder(Path("logs"))

    def open_extensions_folder(self):
        self._open_folder(Path("extensions"))

    def _open_folder(self, folder: Path):
        path = Path(folder).resolve()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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

    # --------------------
    # Setup utilities
    # --------------------
    def install_base_scripts(self):
        script_path = Path("setup/install_defaults.py").resolve()
        if not script_path.exists():
            QMessageBox.warning(self, "Install Base Scripts", "Setup script not found.")
            return

        confirm = QMessageBox.question(
            self,
            "Install Base Scripts",
            "Install default assets and configuration stubs?\n"
            "Existing files remain untouched unless you rerun with --force.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parents[3],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Install Base Scripts", f"Failed to launch installer:\n{exc}")
            return

        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        output = output.strip() or "No output."

        if proc.returncode == 0:
            QMessageBox.information(
                self,
                "Install Base Scripts",
                "Defaults installed successfully.\n\n" + output,
            )
        else:
            QMessageBox.critical(
                self,
                "Install Base Scripts",
                f"Installer exited with code {proc.returncode}.\n\n{output}",
            )


def main():
    app = QApplication(sys.argv)
    try:
        apply_theme(app, 'default_dark')
    except Exception:
        pass
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
