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
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl


LOGGER = logging.getLogger(__name__)


class AudioPanel(QWidget):
    """Simple TTS front end for the `/api/tts/synthesize` endpoint."""

    def __init__(self, base: str = "http://127.0.0.1:8001") -> None:
        super().__init__()
        self.base = base.rstrip("/")

        self.voice_input = QLineEdit(self)
        self.voice_input.setPlaceholderText("Voice (optional, e.g. neutral)")

        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText("Enter text to synthesize")

        synth_btn = QPushButton("Synthesize", self)
        synth_btn.clicked.connect(self._synthesize)

        open_btn = QPushButton("Open Artifact", self)
        open_btn.clicked.connect(self._open_artifact)

        button_row = QHBoxLayout()
        button_row.addWidget(synth_btn)
        button_row.addWidget(open_btn)
        button_row.addStretch(1)

        self.status_label = QLabel("Ready", self)
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.voice_input)
        layout.addWidget(self.text_edit, 1)
        layout.addLayout(button_row)
        layout.addWidget(self.status_label)

        self._last_artifact: Optional[str] = None

    def _synthesize(self) -> None:
        text = self.text_edit.toPlainText().strip()
        if not text:
            self.status_label.setText("Enter text to synthesize.")
            return

        payload = {"text": text}
        voice = self.voice_input.text().strip()
        if voice:
            payload["voice"] = voice

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
        artifact = data.get("artifact") or {}
        path = artifact.get("path")
        self._last_artifact = path
        self.status_label.setText(
            "Synthesis complete. " + (f"Artifact: {path}" if path else "See logs for details.")
        )
        LOGGER.info("TTS generated artifact: %s", path)

    def _open_artifact(self) -> None:
        if not self._last_artifact:
            self.status_label.setText("No artifact to open yet.")
            return
        path = Path(self._last_artifact)
        if not path.exists():
            self.status_label.setText("Artifact path not found; it may have been cleaned up.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

