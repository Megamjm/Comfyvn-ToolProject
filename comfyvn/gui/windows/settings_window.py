from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QDialog, QDockWidget, QVBoxLayout, QWidget

from comfyvn.gui.panels.settings_panel import SettingsPanel


class SettingsWindow(QDialog):
    """Live Fix Stub — Modal settings dialog wrapping the existing panel."""

    def __init__(self, api_client, parent: Optional[object] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(900, 700)

        layout = QVBoxLayout(self)
        panel = SettingsPanel(api_client)
        panel.setParent(self)
        panel.setFeatures(QDockWidget.NoDockWidgetFeatures)
        panel.setTitleBarWidget(QWidget(panel))
        self._panel = panel
        layout.addWidget(panel)
