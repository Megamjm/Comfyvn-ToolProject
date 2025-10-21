from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from comfyvn.assets.audio_manager import AudioManager

LOGGER = logging.getLogger(__name__)


class AudioView(QWidget):
    """
    Lightweight audio control surface that surfaces playback toggles and
    backend status for the studio. Designed for reuse within the Audio Lab.
    """

    def __init__(self, manager: Optional[AudioManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager or AudioManager()

        self.music_toggle = QCheckBox("Music")
        self.voice_toggle = QCheckBox("Voice")
        self.sfx_toggle = QCheckBox("SFX / UI")

        self.backend_label = QLabel(self)
        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

        self._build_ui()
        self._sync_from_manager()

    def _build_ui(self) -> None:
        toggle_box = QGroupBox("Playback Toggles", self)
        toggle_layout = QHBoxLayout()
        toggle_layout.addWidget(self.music_toggle)
        toggle_layout.addWidget(self.voice_toggle)
        toggle_layout.addWidget(self.sfx_toggle)
        toggle_layout.addStretch(1)
        toggle_box.setLayout(toggle_layout)

        save_button = QPushButton("Save Audio Settings", self)
        save_button.clicked.connect(self._handle_save)

        refresh_button = QPushButton("Refresh", self)
        refresh_button.clicked.connect(self._sync_from_manager)

        action_row = QHBoxLayout()
        action_row.addWidget(save_button)
        action_row.addWidget(refresh_button)
        action_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(toggle_box)
        layout.addWidget(self.backend_label)
        layout.addLayout(action_row)
        layout.addWidget(self.status_label)

        self.music_toggle.stateChanged.connect(lambda state: self._on_toggle("music", state))
        self.voice_toggle.stateChanged.connect(lambda state: self._on_toggle("voice", state))
        self.sfx_toggle.stateChanged.connect(lambda state: self._on_toggle("sfx", state))

    def _on_toggle(self, key: str, state: int) -> None:
        enabled = state == Qt.Checked
        LOGGER.debug("AudioView toggle key=%s enabled=%s", key, enabled)
        if key == "music":
            self.manager.set_music_enabled(enabled)
        elif key == "voice":
            self.manager.set_voice_enabled(enabled)
        elif key == "sfx":
            self.manager.set_sfx_enabled(enabled)
        else:  # pragma: no cover - defensive
            return
        self._update_status()

    def _handle_save(self) -> None:
        try:
            self.manager.save_settings()
            self.status_label.setText("Audio settings saved.")
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Failed to save audio settings: %s", exc)
            self.status_label.setText(f"Error saving settings: {exc}")

    def _sync_from_manager(self) -> None:
        """Refresh toggle widgets from the AudioManager state."""
        try:
            self.music_toggle.blockSignals(True)
            self.voice_toggle.blockSignals(True)
            self.sfx_toggle.blockSignals(True)

            self.music_toggle.setChecked(self.manager.is_enabled("music"))
            self.voice_toggle.setChecked(self.manager.is_enabled("voice"))
            # Treat either fx or sound as SFX enablement
            sfx_enabled = self.manager.is_enabled("fx") or self.manager.is_enabled("sound")
            self.sfx_toggle.setChecked(sfx_enabled)
        finally:
            self.music_toggle.blockSignals(False)
            self.voice_toggle.blockSignals(False)
            self.sfx_toggle.blockSignals(False)

        backend_info = getattr(self.manager, "backend_info", "Unknown backend")
        self.backend_label.setText(f"Backend: {backend_info} (master volume {self.manager.master_volume:.2f})")
        self._update_status()

    def _update_status(self) -> None:
        music = "ON" if self.manager.is_enabled("music") else "OFF"
        voice = "ON" if self.manager.is_enabled("voice") else "OFF"
        sfx = "ON" if self.manager.is_enabled("fx") or self.manager.is_enabled("sound") else "OFF"
        self.status_label.setText(f"Music {music} | Voice {voice} | SFX {sfx}")
