from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.services.server_bridge import ServerBridge


@dataclass(slots=True)
class DialogueLine:
    """Normalized representation of a scene dialogue entry."""

    speaker: str
    text: str
    meta: Dict[str, Any]


def _coerce_dialogue(entries: Iterable[Dict[str, Any]]) -> List[DialogueLine]:
    lines: List[DialogueLine] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        speaker = str(raw.get("speaker") or raw.get("name") or "Narrator").strip()
        meta = raw.get("meta")
        lines.append(
            DialogueLine(
                speaker=speaker or "Narrator",
                text=text,
                meta=dict(meta) if isinstance(meta, dict) else {},
            )
        )
    return lines


class VNChatPanel(QWidget):
    """
    Visual novel chat bridge for viewer mode.

    - Mirrors dialogue from imported scenes (`SceneStore` records).
    - Sends ad-hoc prompts to `/api/llm/chat` and displays assistant turns.
    - Optional narrator mode replays the active scene without blocking the UI.
    """

    def __init__(
        self,
        api_client: Optional[ServerBridge] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.api = api_client or ServerBridge()
        self.setObjectName("VNChatPanel")

        self._scenes: List[str] = []
        self._scene_title: Dict[str, str] = {}
        self._scene_dialogue: List[DialogueLine] = []
        self._current_scene_id: Optional[str] = None
        self._history: List[Dict[str, str]] = []
        self._pending = False

        self._narrator_timer = QTimer(self)
        self._narrator_timer.setInterval(2500)
        self._narrator_timer.timeout.connect(self._narrator_step)
        self._narrator_index = 0

        self.scene_selector = QComboBox(self)
        self.scene_selector.currentIndexChanged.connect(self._on_scene_selected)

        self.refresh_button = QPushButton("Refresh Scenes", self)
        self.refresh_button.clicked.connect(self._reload_scenes)

        self.narrator_toggle = QCheckBox("Narrator Mode", self)
        self.narrator_toggle.stateChanged.connect(self._toggle_narrator)

        header = QHBoxLayout()
        header.addWidget(QLabel("Scene:", self))
        header.addWidget(self.scene_selector, 1)
        header.addWidget(self.refresh_button)
        header.addWidget(self.narrator_toggle)

        self.output = QTextBrowser(self)
        self.output.setObjectName("VNChatOutput")
        self.output.setOpenExternalLinks(False)
        self.output.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.output.setPlaceholderText(
            "Scene dialogue and assistant replies appear here."
        )

        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Type a prompt…")
        self.input.returnPressed.connect(self._send_message)

        self.send_button = QPushButton("Send", self)
        self.send_button.clicked.connect(self._send_message)

        entry_row = QHBoxLayout()
        entry_row.addWidget(self.input, 1)
        entry_row.addWidget(self.send_button)

        self.status_label = QLabel(self)
        self.status_label.setObjectName("VNChatStatus")
        self.status_label.setWordWrap(True)
        self._set_status("Ready.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.output, 1)
        layout.addLayout(entry_row)
        layout.addWidget(self.status_label)

        self._reload_scenes()

    # ------------------------------------------------------------------ #
    # Scene handling                                                     #
    # ------------------------------------------------------------------ #
    def _reload_scenes(self) -> None:
        result = self.api.get_json("/sceneio/list", timeout=6.0, default=None)
        items: Iterable[str] = []
        if isinstance(result, dict) and result.get("ok"):
            data = result.get("data")
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                items = data["items"]
            elif isinstance(data, list):
                items = data
            else:
                items = result.get("items") or []
        elif isinstance(result, dict):
            payload = result.get("data") or result.get("items")
            if isinstance(payload, list):
                items = payload

        scenes = [str(item) for item in items if str(item)]
        self._scenes = scenes
        self.scene_selector.blockSignals(True)
        self.scene_selector.clear()
        for scene_id in scenes:
            title = self._scene_title.get(scene_id, scene_id)
            self.scene_selector.addItem(title, userData=scene_id)
        self.scene_selector.blockSignals(False)

        if scenes:
            self.scene_selector.setCurrentIndex(0)
            self._load_scene(scenes[0])
            self._set_status(f"Loaded {len(scenes)} scene(s) from SceneStore.")
        else:
            self._current_scene_id = None
            self._scene_dialogue = []
            self.output.clear()
            self._set_status(
                "No scenes available. Import from SillyTavern or create a scene."
            )

    def _on_scene_selected(self, index: int) -> None:
        if index < 0:
            return
        scene_id = self.scene_selector.itemData(index)
        if scene_id:
            self._load_scene(str(scene_id))

    def _load_scene(self, scene_id: str) -> None:
        params = {"scene_id": scene_id}
        result = self.api.get_json("/sceneio/load", params, timeout=6.0, default=None)
        if not isinstance(result, dict):
            self._set_status("Failed to load scene payload.")
            return

        if not result.get("ok"):
            detail = result.get("error") or result.get("data")
            self._set_status(f"Scene load error: {detail}")
            return

        payload = result.get("data") or {}
        title = str(payload.get("title") or scene_id)
        dialogue_raw = payload.get("dialogue") or payload.get("lines") or []
        dialogue = _coerce_dialogue(dialogue_raw)

        self._scene_title[scene_id] = title
        idx = self.scene_selector.findData(scene_id)
        if idx >= 0:
            self.scene_selector.setItemText(idx, title)

        self._current_scene_id = scene_id
        self._scene_dialogue = dialogue
        self._history.clear()
        self.output.clear()

        if dialogue:
            for line in dialogue:
                self._append_scene_line(line)
            self._set_status(f"{title} • {len(dialogue)} line(s) loaded.")
        else:
            self._set_status(f"{title} has no dialogue yet.")

        self._reset_narrator()

    # ------------------------------------------------------------------ #
    # Chat handling                                                      #
    # ------------------------------------------------------------------ #
    def _send_message(self) -> None:
        if self._pending:
            return
        message = self.input.text().strip()
        if not message:
            return
        self.input.clear()
        self._append_chat_turn("You", message)
        self._history.append({"role": "user", "content": message})
        self._set_status("Sending prompt…")
        self._set_pending(True)

        context = [
            {"speaker": line.speaker, "text": line.text, "meta": line.meta}
            for line in self._scene_dialogue[-12:]
        ]
        payload = {
            "message": message,
            "scene_id": self._current_scene_id,
            "history": list(self._history),
            "context": context,
        }

        self.api.post_json(
            "/api/llm/chat",
            payload,
            timeout=30.0,
            cb=lambda result: QTimer.singleShot(
                0, lambda: self._handle_chat_result(result)
            ),
        )

    def _handle_chat_result(self, result: Dict[str, Any]) -> None:
        self._set_pending(False)
        if not isinstance(result, dict):
            self._set_status("Chat request failed.")
            return
        if not result.get("ok"):
            detail = result.get("error") or result.get("data")
            self._append_system(f"[error] {detail}")
            self._set_status("Assistant request failed.")
            return

        payload = result.get("data") or {}
        reply = str(payload.get("reply") or "").strip()
        provider = payload.get("provider")
        model = payload.get("model")
        meta_bits = []
        if provider:
            meta_bits.append(str(provider))
        if model:
            meta_bits.append(str(model))
        if reply:
            label = "Assistant"
            if meta_bits:
                label += f" ({', '.join(meta_bits)})"
            self._append_chat_turn(label, reply)
            self._history.append({"role": "assistant", "content": reply})
            self._set_status("Assistant reply received.")
        else:
            self._append_system("[notice] No reply from provider.")
            self._set_status("No response content received.")

    # ------------------------------------------------------------------ #
    # Narrator mode                                                      #
    # ------------------------------------------------------------------ #
    def _toggle_narrator(self, state: int) -> None:
        active = state == Qt.Checked
        if active and not self._scene_dialogue:
            self._set_status("Narrator mode requires a loaded scene.")
            self.narrator_toggle.blockSignals(True)
            self.narrator_toggle.setChecked(False)
            self.narrator_toggle.blockSignals(False)
            return
        if active:
            self._set_status("Narrator mode active.")
            self._narrator_timer.start()
        else:
            self._set_status("Narrator mode stopped.")
            self._narrator_timer.stop()

    def _narrator_step(self) -> None:
        if not self._scene_dialogue:
            self._narrator_timer.stop()
            return
        if self._narrator_index >= len(self._scene_dialogue):
            self._append_system("[narrator] End of scene reached.")
            self._narrator_timer.stop()
            self.narrator_toggle.blockSignals(True)
            self.narrator_toggle.setChecked(False)
            self.narrator_toggle.blockSignals(False)
            self._set_status("Narrator mode paused at end of scene.")
            return
        line = self._scene_dialogue[self._narrator_index]
        self._narrator_index += 1
        self._append_scene_line(line, prefix="[live]")

    def _reset_narrator(self) -> None:
        self._narrator_timer.stop()
        self._narrator_index = 0
        self.narrator_toggle.blockSignals(True)
        self.narrator_toggle.setChecked(False)
        self.narrator_toggle.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Formatting helpers                                                 #
    # ------------------------------------------------------------------ #
    def _append_scene_line(self, line: DialogueLine, prefix: str | None = None) -> None:
        tag = f"{prefix} " if prefix else ""
        self.output.append(f"{tag}<b>{line.speaker}:</b> {line.text}")

    def _append_chat_turn(self, speaker: str, text: str) -> None:
        safe_speaker = speaker or "Assistant"
        self.output.append(
            f"<span style='color:#3b82f6'><b>{safe_speaker}:</b></span> {text}"
        )

    def _append_system(self, text: str) -> None:
        self.output.append(f"<span style='color:#6b7280'><i>{text}</i></span>")

    def _set_pending(self, pending: bool) -> None:
        self._pending = pending
        self.send_button.setDisabled(pending)
        self.input.setDisabled(pending)

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)
