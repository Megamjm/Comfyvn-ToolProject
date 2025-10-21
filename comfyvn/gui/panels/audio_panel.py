from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from comfyvn.assets.character_manager import CharacterManager

LOGGER = logging.getLogger(__name__)


class AudioPanel(QWidget):
    """TTS and music utilities with character-aware `/api/tts/speak` tester."""

    def __init__(self, base: str = "http://127.0.0.1:8001") -> None:
        super().__init__()
        self.base = base.rstrip("/")
        self._character_manager = CharacterManager()
        self._characters: Dict[str, Dict[str, Any]] = {}
        self._selected_character_id: Optional[str] = None
        self._active_character_seed: Optional[int] = None

        # ── TTS Inputs ───────────────────────────────────────────────
        self.voice_input = QLineEdit(self)
        self.voice_input.setPlaceholderText("Voice (e.g. neutral)")

        self.lang_input = QLineEdit(self)
        self.lang_input.setPlaceholderText("Language code (optional)")

        self.style_input = QLineEdit(self)
        self.style_input.setPlaceholderText("Style/preset (optional)")

        self.model_input = QLineEdit(self)
        self.model_input.setPlaceholderText("Model or pipeline id (optional)")

        self.character_selector = QComboBox(self)
        self.character_selector.setEnabled(False)
        self.character_selector.currentIndexChanged.connect(self._apply_character_voice)

        self.character_input = QLineEdit(self)
        self.character_input.setPlaceholderText("Character ID (auto from preset)")

        self.scene_input = QLineEdit(self)
        self.scene_input.setPlaceholderText("Scene ID (optional)")

        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText("Enter text to synthesize")

        synth_btn = QPushButton("Synthesize", self)
        synth_btn.clicked.connect(self._synthesize)

        open_btn = QPushButton("Open Artifact", self)
        open_btn.clicked.connect(self._open_artifact)

        open_sidecar_btn = QPushButton("Open Sidecar", self)
        open_sidecar_btn.clicked.connect(self._open_sidecar)

        button_row = QHBoxLayout()
        button_row.addWidget(synth_btn)
        character_btn = QPushButton("Speak Character", self)
        character_btn.clicked.connect(self._speak_character)
        button_row.addWidget(character_btn)
        button_row.addWidget(open_btn)
        button_row.addWidget(open_sidecar_btn)
        button_row.addStretch(1)

        self.status_label = QLabel("Ready", self)
        self.status_label.setWordWrap(True)

        preset_widget = QWidget(self)
        preset_layout = QHBoxLayout(preset_widget)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.addWidget(self.character_selector, 1)
        self.character_reload_btn = QPushButton("Reload", self)
        self.character_reload_btn.clicked.connect(self._load_characters)
        preset_layout.addWidget(self.character_reload_btn, 0)

        self.character_status = QLabel("Loading character presets...", self)
        self.character_status.setWordWrap(True)

        tts_form = QFormLayout()
        tts_form.addRow("Preset", preset_widget)
        tts_form.addRow("Voice", self.voice_input)
        tts_form.addRow("Language", self.lang_input)
        tts_form.addRow("Style", self.style_input)
        tts_form.addRow("Model", self.model_input)
        tts_form.addRow("Character", self.character_input)
        tts_form.addRow("Scene", self.scene_input)

        tts_box = QGroupBox("Text-to-Speech")
        tts_layout = QVBoxLayout()
        tts_layout.addLayout(tts_form)
        tts_layout.addWidget(self.text_edit, 1)
        tts_layout.addLayout(button_row)
        tts_layout.addWidget(self.character_status)
        tts_layout.addWidget(self.status_label)
        tts_box.setLayout(tts_layout)

        # ── Music Remix Inputs ──────────────────────────────────────
        self.music_scene_input = QLineEdit(self)
        self.music_scene_input.setPlaceholderText("scene.demo")
        self.music_style_input = QLineEdit(self)
        self.music_style_input.setPlaceholderText("lofi / upbeat / tense ...")
        self.music_source_input = QLineEdit(self)
        self.music_source_input.setPlaceholderText("Optional source track path/uid")
        self.music_tags_input = QLineEdit(self)
        self.music_tags_input.setPlaceholderText("Comma separated mood tags")
        self.music_seed_input = QSpinBox(self)
        self.music_seed_input.setRange(0, 2_000_000_000)
        self.music_seed_input.setSpecialValueText("Random")

        remix_btn = QPushButton("Remix Music", self)
        remix_btn.clicked.connect(self._remix_music)

        self.remix_status = QLabel("Music remix ready.", self)
        self.remix_status.setWordWrap(True)

        music_form = QFormLayout()
        music_form.addRow("Scene", self.music_scene_input)
        music_form.addRow("Target Style", self.music_style_input)
        music_form.addRow("Source Track", self.music_source_input)
        music_form.addRow("Mood Tags", self.music_tags_input)
        music_form.addRow("Seed", self.music_seed_input)

        music_box = QGroupBox("Music Remix")
        music_layout = QVBoxLayout()
        music_layout.addLayout(music_form)
        music_layout.addWidget(remix_btn, 0)
        music_layout.addWidget(self.remix_status)
        music_box.setLayout(music_layout)

        layout = QVBoxLayout(self)
        layout.addWidget(tts_box, 2)
        layout.addWidget(music_box, 1)

        self._last_artifact: Optional[str] = None
        self._last_sidecar: Optional[str] = None
        self._last_music_artifact: Optional[str] = None
        self._load_characters()

    def _load_characters(self, _checked: bool = False) -> None:
        try:
            records = self._character_manager.list_characters()
        except Exception as exc:  # pragma: no cover - defensive guard
            LOGGER.warning("Failed to load characters: %s", exc)
            records = []

        self._characters.clear()
        self.character_selector.blockSignals(True)
        self.character_selector.clear()
        self._selected_character_id = None
        self._active_character_seed = None

        if not records:
            self.character_selector.addItem("No characters found", None)
            self.character_selector.setEnabled(False)
            self.character_status.setText("No characters registered yet.")
            self.character_selector.blockSignals(False)
            return

        self.character_selector.setEnabled(True)
        for record in records:
            char_id = record.get("id")
            if not char_id:
                continue
            display = record.get("display_name") or record.get("name") or char_id
            self.character_selector.addItem(display, char_id)
            self._characters[char_id] = record
        self.character_selector.blockSignals(False)

        if self.character_selector.count() > 0:
            self.character_selector.setCurrentIndex(0)
            self._apply_character_voice(self.character_selector.currentIndex())
            self.character_status.setText(
                f"Loaded {len(self._characters)} character presets."
            )
        else:
            self.character_selector.addItem("No characters found", None)
            self.character_selector.setEnabled(False)
            self.character_status.setText("No valid character presets found.")

    def _apply_character_voice(self, index: int) -> None:
        char_id = self.character_selector.itemData(index)
        if not char_id:
            self._selected_character_id = None
            self._active_character_seed = None
            return

        record = self._characters.get(char_id)
        if not record:
            return

        self._selected_character_id = char_id
        self.character_input.setText(char_id)

        voice_cfg = record.get("voice") or {}
        if isinstance(voice_cfg, dict):
            voice_name = (
                voice_cfg.get("profile")
                or voice_cfg.get("voice")
                or voice_cfg.get("id")
                or voice_cfg.get("name")
            )
            if voice_name:
                self.voice_input.setText(str(voice_name))
            style_value = voice_cfg.get("style") or voice_cfg.get("preset")
            if style_value:
                self.style_input.setText(str(style_value))
            lang_value = voice_cfg.get("lang")
            if lang_value:
                self.lang_input.setText(str(lang_value))
            model_value = voice_cfg.get("model") or voice_cfg.get("model_hash")
            if model_value:
                self.model_input.setText(str(model_value))
            seed_value = voice_cfg.get("seed") or voice_cfg.get("tts_seed")
            if seed_value is not None:
                try:
                    self._active_character_seed = int(seed_value)
                except (TypeError, ValueError):
                    self._active_character_seed = None
            else:
                self._active_character_seed = None
        else:
            self._active_character_seed = None

        display_name = record.get("display_name") or record.get("name") or char_id
        self.character_status.setText(f"Preset applied for {display_name}")

    def _speak_character(self) -> None:
        if not self._selected_character_id:
            self.status_label.setText("Select a character preset before speaking.")
            return
        if not self.character_input.text().strip():
            self.character_input.setText(self._selected_character_id)
        self._synthesize()

    def _synthesize(self) -> None:
        text = self.text_edit.toPlainText().strip()
        if not text:
            self.status_label.setText("Enter text to synthesize.")
            return

        payload = {"text": text}
        voice = self.voice_input.text().strip()
        if voice:
            payload["voice"] = voice
        lang = self.lang_input.text().strip()
        if lang:
            payload["lang"] = lang
        style = self.style_input.text().strip()
        if style:
            payload["style"] = style
        model = self.model_input.text().strip()
        if model:
            payload["model"] = model
        character = self.character_input.text().strip()
        if character:
            payload["character_id"] = character
        scene = self.scene_input.text().strip()
        if scene:
            payload["scene_id"] = scene
        if (
            self._selected_character_id
            and payload.get("character_id") == self._selected_character_id
            and self._active_character_seed is not None
        ):
            payload["seed"] = self._active_character_seed
        try:
            response = requests.post(
                self.base + "/api/tts/speak",
                json=payload,
                timeout=10,
            )
        except Exception as exc:
            LOGGER.error("TTS request failed: %s", exc)
            self.status_label.setText(f"Error contacting TTS endpoint: {exc}")
            return

        if response.status_code >= 400:
            self.status_label.setText(
                f"TTS error: {response.status_code} {response.text}"
            )
            LOGGER.warning(
                "TTS returned error %s: %s", response.status_code, response.text
            )
            return

        data = response.json()
        artifact = data.get("artifact")
        sidecar = data.get("sidecar")
        cached = data.get("cached", False)

        self._last_artifact = artifact
        self._last_sidecar = sidecar

        voice_out = data.get("voice") or voice or "default"
        lang_out = data.get("lang") or lang or "default"
        style_out = data.get("style") or style or "default"

        info_meta = data.get("info", {}).get("metadata", {})
        model_id = info_meta.get("model") or info_meta.get("model_hash") or "-"
        route = data.get("info", {}).get("route") or "api.tts.speak"
        seed_info = data.get("info", {}).get("seed")

        details = f"voice={voice_out} lang={lang_out} style={style_out} cached={cached} model={model_id}"
        if seed_info is not None:
            details += f" seed={seed_info}"
        details += f" route={route}"
        path_note = artifact or "(no artifact path returned)"
        self.status_label.setText(f"Synthesis complete → {path_note}\n{details}")
        LOGGER.info("TTS generated artifact=%s cached=%s", artifact, cached)

    def _open_artifact(self) -> None:
        if not self._last_artifact:
            self.status_label.setText("No artifact to open yet.")
            return
        path = Path(self._last_artifact)
        if not path.exists():
            self.status_label.setText(
                "Artifact path not found; it may have been cleaned up."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _open_sidecar(self) -> None:
        if not self._last_sidecar:
            self.status_label.setText("No sidecar recorded yet.")
            return
        path = Path(self._last_sidecar)
        if not path.exists():
            self.status_label.setText(
                "Sidecar path not found; verify cache/audio setup."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _remix_music(self) -> None:
        scene = self.music_scene_input.text().strip()
        style = self.music_style_input.text().strip()
        if not scene or not style:
            self.remix_status.setText("Provide both scene and target style for remix.")
            return

        payload = {"scene_id": scene, "target_style": style}
        source = self.music_source_input.text().strip()
        if source:
            payload["source_track"] = source
        tags = self.music_tags_input.text().strip()
        if tags:
            payload["mood_tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        seed = self.music_seed_input.value()
        if seed != 0:
            payload["seed"] = seed

        try:
            response = requests.post(
                self.base + "/api/music/remix",
                json=payload,
                timeout=15,
            )
        except Exception as exc:
            LOGGER.error("Music remix request failed: %s", exc)
            self.remix_status.setText(f"Music remix error: {exc}")
            return

        if response.status_code >= 400:
            self.remix_status.setText(
                f"Remix error: {response.status_code} {response.text}"
            )
            LOGGER.warning(
                "Remix returned error %s: %s", response.status_code, response.text
            )
            return

        data = response.json()
        artifact = data.get("artifact")
        sidecar = data.get("sidecar")
        info = data.get("info", {})
        self._last_music_artifact = artifact

        self.remix_status.setText(
            "Remix generated "
            + (artifact or "(no artifact path)")
            + f"\nscene={info.get('scene_id')} style={info.get('target_style')} tags={info.get('mood_tags')}"
        )
        LOGGER.info(
            "Music remix artifact=%s scene=%s style=%s",
            artifact,
            info.get("scene_id"),
            info.get("target_style"),
        )
