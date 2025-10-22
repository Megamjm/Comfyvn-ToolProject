from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.panels.settings_panel import SettingsPanel


class SettingsWindow(QDialog):
    """Live Fix Stub — Modal settings dialog wrapping the existing panel."""

    def __init__(self, api_client, parent: Optional[object] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(900, 700)

        layout = QVBoxLayout(self)
        self._panel = SettingsPanel(api_client)
        panel = self._panel
        panel.setParent(self)
        panel.setFeatures(QDockWidget.NoDockWidgetFeatures)
        panel.setTitleBarWidget(QWidget(panel))
        layout.addWidget(panel)

        button_row = QHBoxLayout()
        button_row.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        self._btn_save = QPushButton("Save Settings", self)
        self._btn_cancel = QPushButton("Cancel", self)
        button_row.addWidget(self._btn_save)
        button_row.addWidget(self._btn_cancel)
        layout.addLayout(button_row)

        self._btn_save.clicked.connect(self._save_and_close)
        self._btn_cancel.clicked.connect(self._maybe_close)
        panel.settings_changed.connect(self._on_settings_changed)
        panel.settings_saved.connect(self._on_settings_saved)

        self._pending_close = False
        self._dirty = False

    def _on_settings_changed(self) -> None:
        self._dirty = True

    def _on_settings_saved(self) -> None:
        self._dirty = False

    def _save_and_close(self) -> None:
        self._panel._persist_comfy_config()
        self._panel.reset_dirty()
        self.accept()

    def _maybe_close(self) -> None:
        if not self._dirty or not self._panel.is_dirty():
            self.reject()
            return
        answer = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Settings have changed. Save before closing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Cancel:
            return
        if answer == QMessageBox.Save:
            self._save_and_close()
        else:
            self._panel.reset_dirty()
            self.reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._dirty and self._panel.is_dirty():
            answer = QMessageBox.question(
                self,
                "Unsaved Changes",
                "Settings have changed. Save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if answer == QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.Save:
                self._save_and_close()
                event.accept()
                return
            self._panel.reset_dirty()
        event.accept()
