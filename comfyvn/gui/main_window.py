# comfyvn/gui/main_window.py
# 🎨 GUI Code Production Chat Scaffold (expanded)
# [🎨 GUI Code Production Chat]

# comfyvn/gui/main_window.py
# 🎨 GUI Code Production Chat — Headless Detection + Mock Render Support

import os
import sys

# --- Auto-detect headless environment and fallback to offscreen mode ---
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    print("[ComfyVN] No display detected → running in headless/offscreen mode")

# --- Optional: Pre-create a dummy runtime directory for Qt if missing ---
if not os.environ.get("XDG_RUNTIME_DIR"):
    os.environ["XDG_RUNTIME_DIR"] = "/tmp/runtime-comfyvn"
    os.makedirs(os.environ["XDG_RUNTIME_DIR"], exist_ok=True)

# --- Optional: Override Qt's default SIGINT behavior for clean shutdown ---
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)
# --- End headless detection and setup ---

# comfyvn/gui/main_window.py
# Auto-detect and fallback to offscreen when DISPLAY is not set
import os
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QStatusBar,
    QDockWidget, QTextEdit, QFileDialog, QMessageBox
)

from comfyvn.gui.settings_ui import SettingsUI
from comfyvn.gui.asset_browser import AssetBrowser
from comfyvn.gui.playground_ui import PlaygroundUI



DEFAULT_CONFIG_PATH = Path("comfyvn.json")


class MainWindow(QMainWindow):
    """Main application window for ComfyVN GUI.
    Tabs:
      - Settings
      - Asset Browser
      - Playground (preview, layers, prompt-driven edits)
    Provides: log dock, simple menu, config load/save.
    """
    settings_changed = Signal(dict)  # rebroadcast for children

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        super().__init__()
        self.setWindowTitle("ComfyVN")
        self.resize(1440, 900)
        self._config_path = config_path

        # --- Status Bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # --- Central Tabs
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # --- Widgets
        self.settings_ui = SettingsUI(config_path=str(self._config_path))
        self.asset_browser = AssetBrowser()
        self.playground = PlaygroundUI()

        # Tab order
        self.tabs.addTab(self.settings_ui, "Settings")
        self.tabs.addTab(self.asset_browser, "Assets")
        self.tabs.addTab(self.playground, "Playground")

        # --- Log Dock
        self.log_dock = QDockWidget("Logs", self)
        self.log_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_dock.setWidget(self.log_text)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)

        # --- Menu
        self._build_menu()

        # Wire up signals
        self._wire_signals()

        # Attempt initial load
        self._load_config_initial()

    # -------------------- UI Setup --------------------

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

        act_open = QAction("Open Project...", self)
        act_open.triggered.connect(self._open_project)
        file_menu.addAction(act_open)

        act_save = QAction("Save Settings", self)
        act_save.triggered.connect(self._save_settings)
        file_menu.addAction(act_save)

        file_menu.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        tools_menu = menu.addMenu("&Tools")
        act_test_endpoints = QAction("Test Endpoints", self)
        act_test_endpoints.triggered.connect(self.settings_ui.test_endpoints)
        tools_menu.addAction(act_test_endpoints)

        view_menu = menu.addMenu("&View")
        act_toggle_logs = QAction("Toggle Logs", self)
        act_toggle_logs.triggered.connect(
            lambda: self.log_dock.setVisible(not self.log_dock.isVisible())
        )
        view_menu.addAction(act_toggle_logs)

    def _wire_signals(self):
        # Settings propagate to subsystems
        self.settings_ui.settings_changed.connect(self._on_settings_changed)
        self.settings_ui.log_message.connect(self._log)

        # Asset Browser hooks
        self.asset_browser.request_log.connect(self._log)
        self.asset_browser.request_settings.connect(self._current_settings)
        self.asset_browser.request_settings_changed.connect(self._on_settings_changed)

        # Playground hooks
        self.playground.request_log.connect(self._log)
        self.playground.request_settings.connect(self._current_settings)
        self.playground.request_settings_changed.connect(self._on_settings_changed)

    def _load_config_initial(self):
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.settings_ui.apply_settings(data)
                self._log(f"Loaded settings from {self._config_path}")
            except Exception as e:
                self._log(f"Failed to load {self._config_path}: {e}")

    # -------------------- Slots / Helpers --------------------

    @Slot(dict)
    def _on_settings_changed(self, cfg: dict):
        # bubble up to everyone
        self.settings_changed.emit(cfg)
        self.asset_browser.on_settings_changed(cfg)
        self.playground.on_settings_changed(cfg)
        self._log("Settings updated.")

    @Slot()
    def _save_settings(self):
        cfg = self._current_settings()
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            self._log(f"Settings saved to {self._config_path}")
            QMessageBox.information(self, "Saved", f"Settings saved to {self._config_path}")
        except Exception as e:
            self._log(f"Error saving settings: {e}")
            QMessageBox.critical(self, "Error", str(e))

    @Slot()
    def _open_project(self):
        directory = QFileDialog.getExistingDirectory(self, "Open Project Root")
        if directory:
            self.asset_browser.set_project_root(directory)
            self._log(f"Project root set: {directory}")

    def _current_settings(self) -> dict:
        return self.settings_ui.collect_settings()

    @Slot(str)
    def _log(self, text: str):
        self.log_text.append(text)

        # --- Mock render surface for headless mode ---
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            from PySide6.QtGui import QImage, QPainter
            self._mock_surface = QImage(640, 480, QImage.Format_RGB32)
            self._mock_surface.fill(0)
            painter = QPainter(self._mock_surface)
            painter.drawText(10, 30, "ComfyVN GUI (Headless Mode)")
            painter.end()
            print("[ComfyVN] Mock render surface created (offscreen mode active)")
# -------------------- Main Entry Point --------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
# comfyvn/gui/main_window.py