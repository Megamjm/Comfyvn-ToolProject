import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/gui/world_ui.py
# 🌍 World Manager GUI with integrated StatusBar feedback

from PySide6.QtWidgets import (QComboBox, QFileDialog, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

from comfyvn.core.settings_manager import SettingsManager
from comfyvn.core.world_loader import WorldLoader
from comfyvn.gui.status_bar import StatusBar


class WorldUI(QWidget):
    """Manual world manager for ComfyVN with color-coded status feedback."""

    def __init__(self):
        super().__init__()
        self.loader = WorldLoader()
        self.settings = SettingsManager()
        st_cfg = (self.settings.get("integrations") or {}).get("sillytavern", {})
        default_base = st_cfg.get("base_url", "http://127.0.0.1:8000")
        default_plugin = st_cfg.get("plugin_base", "/api/plugins/comfyvn-data-exporter")
        default_token = st_cfg.get("token") or ""
        default_user = st_cfg.get("user_id") or ""

        # --- Window Setup ---
        self.setWindowTitle("World Manager")
        self.setGeometry(400, 200, 400, 270)
        layout = QVBoxLayout()
        self.setLayout(layout)

        # --- Source Selector ---
        layout.addWidget(QLabel("World Source:"))
        self.source_box = QComboBox()
        self.source_box.addItems(["Local Worlds", "SillyTavern"])
        layout.addWidget(self.source_box)

        # --- API Config ---
        layout.addWidget(QLabel("SillyTavern Base URL:"))
        self.api_input = QLineEdit(default_base)
        layout.addWidget(self.api_input)

        layout.addWidget(QLabel("Plugin Path (relative):"))
        self.plugin_input = QLineEdit(default_plugin)
        layout.addWidget(self.plugin_input)

        layout.addWidget(QLabel("Optional API Token:"))
        self.token_input = QLineEdit(default_token)
        self.token_input.setPlaceholderText("Leave empty if not required")
        layout.addWidget(self.token_input)

        layout.addWidget(QLabel("User ID Override (optional):"))
        self.user_input = QLineEdit(default_user)
        self.user_input.setPlaceholderText("Auto-detect when empty")
        layout.addWidget(self.user_input)

        # --- Local Path ---
        self.path_button = QPushButton("Set Local World Data Path")
        self.path_button.clicked.connect(self.set_data_path)
        layout.addWidget(self.path_button)

        # --- Manual Refresh ---
        self.refresh_button = QPushButton("Manual Refresh (Sync from SillyTavern)")
        self.refresh_button.clicked.connect(self.manual_refresh)
        layout.addWidget(self.refresh_button)

        # --- Status Bar ---
        self.status_bar = StatusBar("Idle: Waiting for user action.")
        layout.addWidget(self.status_bar)

    def set_data_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select World Data Folder")
        if folder:
            self.loader.data_path = folder
            self._set_status("success", f"Data path set: {folder}")

    def manual_refresh(self):
        if self.source_box.currentText() != "SillyTavern":
            self._set_status("warning", "Source not set to SillyTavern.")
            QMessageBox.warning(
                self, "Invalid Source", "Switch to 'SillyTavern' to sync remotely."
            )
            return

        self.loader.configure_remote(
            base_url=self.api_input.text(),
            plugin_base=self.plugin_input.text(),
            token=self.token_input.text() or None,
            user_id=self.user_input.text() or None,
            persist=True,
        )

        result = self.loader.sync_from_sillytavern()
        status = result.get("status")
        message = result.get("message", "")
        updated = result.get("updated", [])

        if status == "success":
            msg = f"{message} ({len(updated)} updated)"
            self._set_status("success", msg)
        elif status == "no_change":
            self._set_status("warning", message)
        else:
            self._set_status("error", message)

    def _set_status(self, state, message):
        """Update both local and global status bars."""
        if hasattr(self, "status_bar") and self.status_bar:
            self.status_bar.set_status(state, message)
