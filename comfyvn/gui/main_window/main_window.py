# comfyvn/gui/main_window/main_window.py
# ComfyVN Studio — Phase 8.6 clean rebuild
# - Dynamic menus via menu_registry
# - Theme Manager applied at launch
# - Studio layout (dock manager + panels)
# - Detached server launcher (manual)
# - Spaces switch + safe stubs for File/Import/Export
# - Keyboard shortcuts (core) + extension hook point

from __future__ import annotations

from pathlib import Path
import sys
import threading
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMessageBox

# Studio shell + infrastructure
from .shell_studio import ShellStudio
from comfyvn.gui.core.dock_manager import DockManager
from comfyvn.gui.core.workspace_controller import WorkspaceController
from comfyvn.gui.services.server_bridge import ServerBridge

# Dynamic menu and theme engine
from comfyvn.core.menu_runtime_bridge import menu_registry
from comfyvn.core.theme_manager import apply_theme

# Panels (guarded load in open_* methods)
# Keep import paths stable; errors handled gracefully when opened.
# - AssetBrowser
# - TimelinePanel
# - PlaygroundPanel
# - RenderPanel
# - SettingsPanel
# - LogsConsole
# - ExtensionsPanel
# - GPULocalPanel
# - GPURemotePanel
# - ServerControlPanel

def _maybe_set_stylesheet(app):
    """Legacy support: if a .qss file exists, it will be applied after theme."""
    try:
        qss = Path("comfyvn/gui/resources/style_dark.qss")
        if qss.exists():
            app.setStyleSheet(app.styleSheet() + "\n" + qss.read_text(encoding="utf-8"))
    except Exception:
        pass

def _launch_server_process():
    """Launch FastAPI server as independent process (not tied to GUI)."""
    try:
        exe = sys.executable
        script = Path("comfyvn/app.py").resolve()
        log_path = Path("logs/server_detached.log"); log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as log:
            proc = subprocess.Popen([exe, str(script)], stdout=log, stderr=log)
        print(f"[ComfyVN GUI] 🚀 Detached server started (PID={proc.pid})")
        return proc
    except Exception as e:
        print(f"[ComfyVN GUI] ❌ Failed to launch detached server: {e}")
        return None


# ---------------------------------------------------------------------
#  🧱 MainWindow
# ---------------------------------------------------------------------
class MainWindow(ShellStudio):
    def __init__(self):
        super().__init__(title="ComfyVN Studio")
        self.dockman = DockManager(self)
        self.workspace = WorkspaceController(self, Path("data/workspaces"))
        self.bridge = ServerBridge(base="http://127.0.0.1:8001")

        # internal panel refs
        self._assets = self._timeline = self._playground = None
        self._render = self._settings = self._extensions = None
        self._gpu_local = self._gpu_remote = None
        self._console_dock = None

        # Build menus dynamically from registry
        self._ensure_menu_bar()
        self._build_menus_from_registry()

        # Keyboard shortcuts (core set) + extension hook
        self._install_core_shortcuts()
        self._extension_shortcuts_hook()

        # Restore default visible layout
        self._attach_server_control_footer()

    # -----------------------------
    # Menu bar (dynamic)
    # -----------------------------
    def _ensure_menu_bar(self):
        # Provide common menu sections even if registry is empty
        mb = self.menuBar()
        self._sections = {}
        for name in ("File", "View", "Tools", "GPU", "Window", "Spaces", "Help"):
            self._sections[name] = mb.addMenu(name)

    def _build_menus_from_registry(self):
        """Build actions from menu_registry contents."""
        by = menu_registry.by_section()
        # Clear any dynamically-added actions in our sections
        for sec, menu in self._sections.items():
            menu.clear()

        # Populate from registry
        for section, items in by.items():
            if section not in self._sections:
                self._sections[section] = self.menuBar().addMenu(section)
            menu = self._sections[section]
            last_sep = False
            for it in items:
                try:
                    if getattr(it, "separator_before", False) and not last_sep:
                        menu.addSeparator()
                    handler_name = getattr(it, "handler", "")
                    handler = getattr(self, handler_name, None)
                    if handler is None:
                        # fallback safe no-op
                        def _noop():
                            QMessageBox.information(self, "Not Implemented", f"Handler '{handler_name}' is not available.")
                        act = QAction(it.label, self); act.triggered.connect(_noop); menu.addAction(act)
                    else:
                        act = QAction(it.label, self); act.triggered.connect(handler); menu.addAction(act)
                    last_sep = False
                except Exception:
                    # keep menu building resilient
                    pass

        # Minimal built-ins if registry empty
        if not by:
            self._inject_minimal_builtins()

    def _inject_minimal_builtins(self):
        # File
        m = self._sections["File"]
        for lbl, fn in [
            ("New Project", self.new_project),
            ("Save Project", self.save_project),
            ("Load Project", self.load_project),
        ]:
            a = QAction(lbl, self); a.triggered.connect(fn); m.addAction(a)
        m.addSeparator()
        a = QAction("Exit", self); a.triggered.connect(lambda: sys.exit(0)); m.addAction(a)

        # View
        m = self._sections["View"]
        for lbl, fn in [
            ("Dashboard", self.open_dashboard),
            ("Assets", self.open_assets),
            ("Timeline", self.open_timeline),
            ("Playground", self.open_playground),
            ("Render Queue", self.open_render),
            ("Settings Panel", self.open_settings_panel),
            ("Logs Console", self.toggle_log_console),
            ("GPU (Local)", self.open_gpu_local),
            ("GPU (Remote)", self.open_gpu_remote),
            ("Extensions", self.open_extensions),
        ]:
            a = QAction(lbl, self); a.triggered.connect(fn); m.addAction(a)

        # Tools
        m = self._sections["Tools"]
        a = QAction("Start Server (detached)", self); a.triggered.connect(self.start_server_manual); m.addAction(a)
        a = QAction("Save Workspace", self); a.triggered.connect(self.save_workspace); m.addAction(a)
        a = QAction("Load Workspace", self); a.triggered.connect(self.load_workspace); m.addAction(a)

        # Spaces
        m = self._sections["Spaces"]
        for lbl, fn in [
            ("Render Space", lambda: self.open_space("Render")),
            ("Import Space", lambda: self.open_space("Import")),
            ("GPU Space",    lambda: self.open_space("GPU")),
            ("Editor Space", lambda: self.open_space("Editor")),
            ("System",       lambda: self.open_space("System")),
        ]:
            a = QAction(lbl, self); a.triggered.connect(fn); m.addAction(a)

    # -----------------------------
    # Shortcuts
    # -----------------------------
    def _install_core_shortcuts(self):
        # File-like shortcuts
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_project)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_project)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.load_project)
        # View toggles
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.toggle_log_console)
        # Spaces
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.open_space("Editor"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.open_space("Render"))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda: self.open_space("Import"))
        QShortcut(QKeySequence("Ctrl+4"), self, activated=lambda: self.open_space("GPU"))
        QShortcut(QKeySequence("Ctrl+5"), self, activated=lambda: self.open_space("System"))

    def _extension_shortcuts_hook(self):
        """Hook point: extensions can register their own shortcuts via a known API."""
        try:
            from comfyvn.core.extension_gui_bridge import bridge  # if present
            reg = getattr(bridge, "register_shortcuts_for_window", None)
            if callable(reg):
                reg(self)
        except Exception:
            pass

    # -----------------------------
    # Footer: server control
    # -----------------------------
    def _attach_server_control_footer(self):
        try:
            from comfyvn.gui.panels.server_control_panel import ServerControlPanel
            panel = ServerControlPanel()  # keep constructor with no unexpected args
            self.dockman.dock(panel, "Server Control", Qt.BottomDockWidgetArea)
        except Exception as e:
            print(f"[ComfyVN GUI] ⚠️ Failed to initialize Server Control Panel: {e}")

    # -----------------------------
    # Workspace helpers
    # -----------------------------
    def save_workspace(self):
        p = self.workspace.save()
        QMessageBox.information(self, "Workspace", f"Saved layout: {p}")

    def load_workspace(self):
        ok = self.workspace.load()
        QMessageBox.information(self, "Workspace", "Loaded" if ok else "No saved layout")

    # -----------------------------
    # Spaces (presets)
    # -----------------------------
    def open_space(self, name: str):
        print(f"[Spaces] Switching to space: {name}")
        # Minimal behavior: open a sensible set for the space
        if name == "Editor":
            self.open_dashboard()
        elif name == "Render":
            self.open_render(); self.open_assets()
        elif name == "Import":
            self.open_assets(); self.toggle_log_console()
        elif name == "GPU":
            self.open_gpu_local(); self.open_gpu_remote()
        elif name == "System":
            self.toggle_log_console()
        else:
            self.open_dashboard()

    def open_dashboard(self):
        self.open_assets()
        self.open_timeline()
        self.toggle_log_console()

    # -----------------------------
    # Panel openers (safe)
    # -----------------------------
    def open_assets(self):
        try:
            if not self._assets:
                from comfyvn.gui.panels.asset_browser import AssetBrowser
                self._assets = AssetBrowser()
                self.dockman.dock(self._assets, "Assets")
            else:
                self._assets.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "Assets", str(e))

    def open_timeline(self):
        try:
            if not self._timeline:
                from comfyvn.gui.panels.timeline_panel import TimelinePanel
                self._timeline = TimelinePanel()
                self.dockman.dock(self._timeline, "Timeline")
            else:
                self._timeline.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "Timeline", str(e))

    def open_playground(self):
        try:
            if not self._playground:
                from comfyvn.gui.panels.playground_panel import PlaygroundPanel
                self._playground = PlaygroundPanel(base=self.bridge.base)
                self.dockman.dock(self._playground, "Playground")
            else:
                self._playground.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "Playground", str(e))

    def open_render(self):
        try:
            if not self._render:
                from comfyvn.gui.panels.render_panel import RenderPanel
                self._render = RenderPanel()
                self.dockman.dock(self._render, "Render Queue")
            else:
                self._render.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "Render", str(e))

    def open_settings_panel(self):
        try:
            if not self._settings:
                from comfyvn.gui.panels.settings_panel import SettingsPanel
                self._settings = SettingsPanel(self.bridge)
                self.dockman.dock(self._settings, "Settings")
            else:
                self._settings.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "Settings", str(e))

    def open_extensions(self):
        try:
            if not self._extensions:
                from comfyvn.gui.panels.extensions_panel import ExtensionsPanel
                self._extensions = ExtensionsPanel()
                self.dockman.dock(self._extensions, "Extensions")
            else:
                self._extensions.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "Extensions", str(e))

    def open_gpu_local(self):
        try:
            if not self._gpu_local:
                from comfyvn.gui.panels.gpu_local_panel import GPULocalPanel
                self._gpu_local = GPULocalPanel(base=self.bridge.base)
                self.dockman.dock(self._gpu_local, "GPU / Local")
            else:
                self._gpu_local.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "GPU (Local)", str(e))

    def open_gpu_remote(self):
        try:
            if not self._gpu_remote:
                from comfyvn.gui.panels.gpu_remote_panel import GPURemotePanel
                endpoints = []
                try:
                    cfg = self.bridge.get("REMOTE_GPU_LIST", default="")
                    if cfg:
                        endpoints = [x.strip() for x in cfg.split(",") if x.strip()]
                except Exception:
                    pass
                self._gpu_remote = GPURemotePanel(endpoints=endpoints)
                self.dockman.dock(self._gpu_remote, "GPU / Remote")
            else:
                self._gpu_remote.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "GPU (Remote)", str(e))

    def toggle_log_console(self):
        try:
            if not self._console_dock:
                from comfyvn.gui.panels.logs_console import LogsConsole
                self._console = LogsConsole()
                self._console_dock = self.dockman.dock(self._console, "Logs")
            else:
                self._console_dock.setVisible(not self._console_dock.isVisible())
        except Exception as e:
            QMessageBox.critical(self, "Logs", str(e))

    # -----------------------------
    # Tools
    # -----------------------------
    def start_server_manual(self):
        proc = _launch_server_process()
        if not proc:
            QMessageBox.critical(self, "Server", "Failed to start detached process.")
        else:
            QMessageBox.information(self, "Server", f"Server started (PID {proc.pid}) — close manually if needed.\nhttp://127.0.0.1:8001")

    # -----------------------------
    # File / Import / Export — stubs
    # -----------------------------
    def new_project(self):
        QMessageBox.information(self, "New Project", "Stub — implement project scaffolding here.")

    def save_project(self):
        QMessageBox.information(self, "Save Project", "Stub — implement save here.")

    def save_project_as(self):
        QMessageBox.information(self, "Save Project As…", "Stub — implement save-as dialog here.")

    def load_project(self):
        QMessageBox.information(self, "Load Project", "Stub — implement load dialog here.")

    def export_to_renpy(self):
        QMessageBox.information(self, "Export", "Stub — export to Ren’Py package (.rpy).")

    def import_manga(self):
        QMessageBox.information(self, "Import", "Stub — import manga ZIP/Folder.")

    def import_vn(self):
        QMessageBox.information(self, "Import", "Stub — import VN bundle.")

    def import_assets(self):
        QMessageBox.information(self, "Import", "Stub — import sprites/audio/backgrounds.")


# ---------------------------------------------------------------------
# 🚀 Entry Point
# ---------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    try:
        apply_theme(app, "default_dark")
    except Exception:
        pass
    _maybe_set_stylesheet(app)

    w = MainWindow()
    w.show()
    sys.exit(app.exec())
