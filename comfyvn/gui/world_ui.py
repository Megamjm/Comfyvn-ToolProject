# comfyvn/gui/world_ui.py
# 🌍 World Manager GUI with integrated StatusBar feedback

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton,
    QFileDialog, QLineEdit, QMessageBox
)
from comfyvn.modules.sync.world_loader import WorldLoader
from gui.components.status_bar import StatusBar


class WorldUI(QWidget):
    """Manual world manager for ComfyVN with color-coded status feedback."""

    def __init__(self):
        super().__init__()
        self.loader = WorldLoader()

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
        layout.addWidget(QLabel("SillyTavern API URL:"))
        self.api_input = QLineEdit("http://127.0.0.1:8000/api/v1/lorebooks")
        layout.addWidget(self.api_input)

        layout.addWidget(QLabel("Optional API Token:"))
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Leave empty if not required")
        layout.addWidget(self.token_input)

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
            QMessageBox.warning(self, "Invalid Source", "Switch to 'SillyTavern' to sync remotely.")
            return

        self.loader.bridge.api_url = self.api_input.text()
        self.loader.bridge.token = self.token_input.text()

        result = self.loader.sync_from_sillytavern()
        status = result.get("status")
        message = result.get("message", "")
        updated = result.get("updated", [])

        if status == "success":
            msg = f"{message} ({len(updated)} updated)"
            self._set_status("success", msg)
        elif status == "no_changes":
            self._set_status("warning", message)
        else:
            self._set_status("error", message)

    def _set_status(self, state, message):
        """Update both local and global status bars."""
        if hasattr(self, "status_bar") and self.status_bar:
            self.status_bar.set_status(state, message)
