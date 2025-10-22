from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QDialog, QVBoxLayout

from comfyvn.gui.panels.settings_panel import SettingsPanel


class SettingsWindow(QDialog):
    """Live Fix Stub — Modal settings dialog wrapping the existing panel."""

    def __init__(self, api_client, parent: Optional[object] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(900, 700)

        layout = QVBoxLayout(self)
        layout.addWidget(SettingsPanel(api_client, parent=self))
