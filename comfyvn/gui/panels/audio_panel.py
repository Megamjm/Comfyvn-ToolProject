from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import requests
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QFormLayout,
    QSpinBox,
    QGroupBox,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl


LOGGER = logging.getLogger(__name__)


class AudioPanel(QWidget):
    """Simple TTS front end for the `/api/tts/synthesize` endpoint."""

    def __init__(self, base: str = "http://127.0.0.1:8001") -> None:
        super().__init__()
        self.base = base.rstrip("/")

        # ── TTS Inputs ───────────────────────────────────────────────
        self.voice_input = QLineEdit(self)
        self.voice_input.setPlaceholderText("Voice (e.g. neutral)")

        self.lang_input = QLineEdit(self)
        self.lang_input.setPlaceholderText("Language code (optional)")

        self.style_input = QLineEdit(self)
        self.style_input.setPlaceholderText("Style/preset (optional)")

        self.model_input = QLineEdit(self)
        self.model_input.setPlaceholderText("Model or pipeline id (optional)")

        self.character_input = QLineEdit(self)
        self.character_input.setPlaceholderText("Character ID (optional)")

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
        button_row.addWidget(open_btn)
        button_row.addWidget(open_sidecar_btn)
        button_row.addStretch(1)

        self.status_label = QLabel("Ready", self)
        self.status_label.setWordWrap(True)

        tts_form = QFormLayout()
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

        try:
            response = requests.post(
                self.base + "/api/tts/synthesize",
                json=payload,
                timeout=10,
            )
        except Exception as exc:
            LOGGER.error("TTS request failed: %s", exc)
            self.status_label.setText(f"Error contacting TTS endpoint: {exc}")
            return

        if response.status_code >= 400:
            self.status_label.setText(f"TTS error: {response.status_code} {response.text}")
            LOGGER.warning("TTS returned error %s: %s", response.status_code, response.text)
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

        details = f"voice={voice_out} lang={lang_out} style={style_out} cached={cached} model={model_id}"
        path_note = artifact or "(no artifact path returned)"
        self.status_label.setText(f"Synthesis complete → {path_note}\n{details}")
        LOGGER.info("TTS generated artifact=%s cached=%s", artifact, cached)

    def _open_artifact(self) -> None:
        if not self._last_artifact:
            self.status_label.setText("No artifact to open yet.")
            return
        path = Path(self._last_artifact)
        if not path.exists():
            self.status_label.setText("Artifact path not found; it may have been cleaned up.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _open_sidecar(self) -> None:
        if not self._last_sidecar:
            self.status_label.setText("No sidecar recorded yet.")
            return
        path = Path(self._last_sidecar)
        if not path.exists():
            self.status_label.setText("Sidecar path not found; verify cache/audio setup.")
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
            self.remix_status.setText(f"Remix error: {response.status_code} {response.text}")
            LOGGER.warning("Remix returned error %s: %s", response.status_code, response.text)
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
        LOGGER.info("Music remix artifact=%s scene=%s style=%s", artifact, info.get("scene_id"), info.get("target_style"))
