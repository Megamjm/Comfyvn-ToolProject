from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from comfyvn.core.scene_store import SceneStore
from comfyvn.gui.panels.json_endpoint_panel import JsonEndpointPanel, PanelAction
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.importers.silly_persona import iter_chat_payloads, iter_persona_payloads

PROMPT_LIBRARY: List[Tuple[str, str]] = [
    (
        "Scene Summary & Story Beats",
        "Summarise the scene in 3 sentences, list the key story beats, and note any cliffhangers or unresolved threads.",
    ),
    (
        "Character Spotlight",
        "Identify each speaker, describe their mood, motivations, and any changes compared to earlier dialogue. Flag inconsistencies.",
    ),
    (
        "World & Setting Extraction",
        "Extract locations, time-of-day cues, world lore references, and props mentioned. Provide suggestions for background art.",
    ),
    (
        "Action Breakdown",
        "List physical actions and reactions in order, identify combat or dramatic moments, and propose staging notes for sprites.",
    ),
    (
        "Continuity & Tone Audit",
        "Evaluate tone, pacing, and continuity. Highlight shifts in mood, potential tonal clashes, and where comedic/serious beats occur.",
    ),
    (
        "Adaptation Plan",
        "Transform the chat into VN-ready structure: propose scene titles, choice points, and optional narration inserts for clarity.",
    ),
]


def _format_participants(messages: Sequence[dict[str, Any]]) -> str:
    seen: List[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        speaker = (
            message.get("name")
            or message.get("speaker")
            or message.get("author")
            or message.get("role")
        )
        if isinstance(speaker, str):
            speaker = speaker.strip()
        if not speaker:
            continue
        if speaker not in seen:
            seen.append(speaker)
        if len(seen) >= 4:
            break
    if not seen:
        return "Unknown participants"
    remaining = ""
    if len(seen) == 4:
        remaining = "…"
    return ", ".join(seen[:3]) + remaining


def _format_dialogue(scene: Dict[str, Any]) -> str:
    dialogue = scene.get("dialogue") or []
    lines: List[str] = []
    for entry in dialogue:
        if not isinstance(entry, dict):
            continue
        speaker = entry.get("speaker") or "Narrator"
        text = entry.get("text") or ""
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _chunk_lines(lines: List[str], size: int) -> Iterable[str]:
    if size <= 0:
        yield "\n".join(lines)
        return
    bucket: List[str] = []
    for line in lines:
        bucket.append(line)
        if len(bucket) >= size:
            yield "\n".join(bucket)
            bucket = []
    if bucket:
        yield "\n".join(bucket)


def _iter_world_payloads(payload: Any) -> List[Tuple[str, Dict[str, Any]]]:
    worlds: List[Tuple[str, Dict[str, Any]]] = []
    if payload is None:
        return worlds
    if isinstance(payload, dict):
        if "worlds" in payload:
            return _iter_world_payloads(payload["worlds"])
        if all(isinstance(v, dict) for v in payload.values()):
            for name, data in payload.items():
                label = str(name or data.get("name") or data.get("id") or "World")
                worlds.append((label, dict(data or {})))
            return worlds
        label = str(payload.get("name") or payload.get("id") or "World")
        worlds.append((label, dict(payload)))
        return worlds
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                label = str(item.get("name") or item.get("id") or "World")
                content = (
                    item.get("data") if isinstance(item.get("data"), dict) else item
                )
                worlds.append((label, dict(content or {})))
    return worlds


def _preview_text(value: Any, limit: int = 160) -> str:
    text = ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, list):
        text = "; ".join(str(entry) for entry in value if entry)[: limit * 2]
    elif isinstance(value, dict):
        keys = ", ".join(sorted(value.keys()))
        text = f"keys: {keys}"
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


class ImportManagerPanel(QWidget):
    """Guided importer with presets for SillyTavern assets plus advanced JSON mode."""

    def __init__(self, base_url: str, *, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.bridge = ServerBridge(self.base_url)

        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel("Select an import workflow:"))
        self.selector = QComboBox()
        self.selector.addItem("SillyTavern Chat (guided)", "st_chat")
        self.selector.addItem("SillyTavern Personas (guided)", "st_personas")
        self.selector.addItem("SillyTavern Worlds/Lore (guided)", "st_worlds")
        self.selector.addItem("Roleplay Transcript (guided)", "roleplay")
        self.selector.addItem("Advanced JSON Payloads", "json_raw")
        header.addWidget(self.selector)
        header.addStretch(1)
        layout.addLayout(header)

        self.stack = QStackedWidget()
        self.chat_widget = STChatImportWidget(self.bridge, parent=self)
        self.stack.addWidget(self.chat_widget)
        self.persona_widget = STPersonaImportWidget(self.bridge, parent=self)
        self.stack.addWidget(self.persona_widget)
        self.world_widget = STWorldImportWidget(self.bridge, parent=self)
        self.stack.addWidget(self.world_widget)
        self.roleplay_widget = RoleplayImportWidget(self.bridge, parent=self)
        self.stack.addWidget(self.roleplay_widget)

        actions: Iterable[PanelAction] = [
            PanelAction(
                "SillyTavern → Health Probe",
                "GET",
                "/st/health",
                "Confirm the SillyTavern bridge responds before importing assets.",
            ),
            PanelAction(
                "SillyTavern → Sync Extension",
                "POST",
                "/st/extension/sync",
                "Dry-run the comfyvn-data-exporter sync before distributing to SillyTavern.",
                payload={"dry_run": True},
            ),
            PanelAction(
                "Import Persona Bundle",
                "POST",
                "/st/import",
                "Send a persona bundle exported from SillyTavern.",
                payload={"type": "personas", "data": []},
            ),
            PanelAction(
                "Import Lore Library",
                "POST",
                "/st/import",
                "Import world lore JSON to populate story references.",
                payload={"type": "worlds", "data": []},
            ),
            PanelAction(
                "Import Chat Transcript",
                "POST",
                "/st/import",
                "Convert SillyTavern chat history into ComfyVN scenes.",
                payload={"type": "chats", "data": []},
            ),
            PanelAction(
                "Activate World Snapshot",
                "POST",
                "/st/import",
                "Flag a world snapshot as the active reference world.",
                payload={"type": "active", "data": {"active_world": ""}},
            ),
            PanelAction(
                "Import FurAffinity Gallery",
                "POST",
                "/api/imports/furaffinity",
                "Upload a FurAffinity export payload for ingestion.",
                payload={"collection": []},
            ),
            PanelAction(
                "Import Roleplay Archive",
                "POST",
                "/api/imports/roleplay",
                "Import roleplay transcripts exported as JSON or text blocks.",
                payload={"entries": []},
            ),
        ]
        self.json_widget = JsonEndpointPanel(
            self.base_url,
            title="Advanced Import Requests",
            description=(
                "Use the raw JSON client for debugging or custom importer payloads.\n"
                "Guided flows are available for common SillyTavern exports."
            ),
            actions=actions,
            parent=self,
        )
        self.stack.addWidget(self.json_widget)
        layout.addWidget(self.stack, 1)

        self.selector.currentIndexChanged.connect(self._on_mode_changed)

    def _on_mode_changed(self, index: int) -> None:
        mode = self.selector.itemData(index)
        if mode == "json_raw":
            self.stack.setCurrentWidget(self.json_widget)
        elif mode == "st_personas":
            self.stack.setCurrentWidget(self.persona_widget)
        elif mode == "st_worlds":
            self.stack.setCurrentWidget(self.world_widget)
        elif mode == "roleplay":
            self.stack.setCurrentWidget(self.roleplay_widget)
        else:
            self.stack.setCurrentWidget(self.chat_widget)


class STChatImportWidget(QWidget):
    """Guided SillyTavern chat importer with LLM review hooks."""

    def __init__(self, bridge: ServerBridge, *, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.bridge = bridge
        self.store = SceneStore()
        self._raw_payload: Any = None
        self._chat_entries: List[Dict[str, Any]] = []
        self._last_imported: List[Dict[str, Any]] = []
        self._loaded_path: Optional[Path] = None

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Select a SillyTavern chat export (.json) and import it into SceneStore.\n"
            "The importer analyses participants, queues the REST payload, and offers an optional LLM review step."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        load_row = QHBoxLayout()
        self.load_button = QPushButton("Load Chat Export…")
        self.load_button.clicked.connect(self._load_file)
        load_row.addWidget(self.load_button)
        self.path_label = QLabel("No file selected.")
        self.path_label.setWordWrap(True)
        load_row.addWidget(self.path_label, 1)
        layout.addLayout(load_row)

        summary_group = QGroupBox("Transcript Overview")
        summary_layout = QVBoxLayout(summary_group)
        self.summary_label = QLabel(
            "Load a SillyTavern export to preview participants and turn counts."
        )
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        self.preview_list = QListWidget()
        summary_layout.addWidget(self.preview_list, 1)
        layout.addWidget(summary_group, 1)

        llm_group = QGroupBox("LLM Review (optional)")
        llm_form = QFormLayout(llm_group)
        self.instructions_edit = QPlainTextEdit()
        self.instructions_edit.setPlaceholderText(
            "Summarise each scene, highlight POV changes, and flag any continuity issues."
        )
        self.instructions_edit.setFixedHeight(100)
        llm_form.addRow("Instructions:", self.instructions_edit)
        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(0, 200)
        self.chunk_spin.setValue(40)
        self.chunk_spin.setToolTip(
            "Number of dialogue lines per LLM chunk (0 = entire scene)."
        )
        llm_form.addRow("Lines per chunk:", self.chunk_spin)
        self.auto_llm = QCheckBox("Run LLM review immediately after import")
        llm_form.addRow("", self.auto_llm)
        layout.addWidget(llm_group)

        buttons = QHBoxLayout()
        self.import_button = QPushButton("Import Scenes")
        self.import_button.clicked.connect(self._import_payload)
        self.import_button.setEnabled(False)
        buttons.addWidget(self.import_button)

        self.open_scenes_button = QPushButton("Open Scenes Panel")
        self.open_scenes_button.clicked.connect(
            lambda: self._open_main_window_panel("open_scenes_panel")
        )
        self.open_scenes_button.setEnabled(False)
        buttons.addWidget(self.open_scenes_button)

        self.open_chat_button = QPushButton("Open VN Chat Panel")
        self.open_chat_button.clicked.connect(
            lambda: self._open_main_window_panel("open_vn_chat_panel")
        )
        self.open_chat_button.setEnabled(False)
        buttons.addWidget(self.open_chat_button)

        self.llm_button = QPushButton("Run LLM Review…")
        self.llm_button.clicked.connect(self._run_llm_review)
        self.llm_button.setEnabled(False)
        buttons.addWidget(self.llm_button)

        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SillyTavern Chat Export",
            "",
            "JSON Files (*.json *.jsonl);;All Files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Load Failed", f"Could not read file:\n{exc}")
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(
                self,
                "Invalid JSON",
                f"The selected file is not valid JSON.\n"
                f"Ensure you export using the comfyvn-data-exporter plug-in.\nDetails: {exc}",
            )
            return

        entries = list(iter_chat_payloads(payload))
        if not entries:
            QMessageBox.warning(
                self,
                "Unsupported Payload",
                "No chats were detected in this export. Confirm the file contains SillyTavern conversations.",
            )
            return

        self._raw_payload = payload
        self._chat_entries = entries
        self._loaded_path = Path(path)
        self._last_imported = []
        self._refresh_preview()
        self.import_button.setEnabled(True)
        self.status_label.setText("Payload ready. Review the overview, then import.")

    def _refresh_preview(self) -> None:
        if not self._chat_entries:
            self.summary_label.setText("Load a SillyTavern export to preview chats.")
            self.preview_list.clear()
            return
        stats: List[str] = []
        total_turns = 0
        for entry in self._chat_entries:
            messages = (
                entry.get("messages") or entry.get("chat") or entry.get("entries") or []
            )
            if isinstance(messages, dict):
                messages = messages.get("items") or []
            if not isinstance(messages, list):
                messages = []
            total_turns += len(messages)
        stats.append(f"Detected {len(self._chat_entries)} chat(s)")
        stats.append(f"Approx. {total_turns} message(s)")
        if self._loaded_path:
            stats.append(f"Source: {self._loaded_path.name}")
        self.summary_label.setText(" • ".join(stats))

        self.preview_list.clear()
        for entry in self._chat_entries:
            title = entry.get("title") or entry.get("name") or "Untitled Chat"
            messages = (
                entry.get("messages") or entry.get("chat") or entry.get("entries") or []
            )
            if isinstance(messages, dict):
                messages = messages.get("items") or []
            if not isinstance(messages, list):
                messages = []
            participants = _format_participants(messages)
            item = QListWidgetItem(
                f"{title} — {len(messages)} turn(s) — {participants}"
            )
            self.preview_list.addItem(item)

    def _import_payload(self) -> None:
        if self._raw_payload is None:
            QMessageBox.information(
                self, "No Payload", "Load a SillyTavern export before importing."
            )
            return
        self.import_button.setEnabled(False)
        self.status_label.setText("Importing chats…")
        payload = {"type": "chats", "data": self._raw_payload}
        result = self.bridge.post_json(
            "/st/import", payload, timeout=25.0, default=None
        )
        self.import_button.setEnabled(True)
        if not isinstance(result, dict) or not result.get("ok"):
            detail = ""
            if isinstance(result, dict):
                detail = str(result.get("data") or result.get("error") or "")
            QMessageBox.warning(
                self, "Import Failed", f"Server rejected the payload.\n{detail}"
            )
            self.status_label.setText("Import failed.")
            return
        data = result.get("data") or {}
        imported = data.get("imported") or 0
        self._last_imported = data.get("scenes") or []
        errors = data.get("errors") or []
        summary = f"Imported {imported} scene(s)."
        if errors:
            summary += f" {len(errors)} item(s) reported errors."
        self.status_label.setText(summary)
        self.open_scenes_button.setEnabled(True)
        self.open_chat_button.setEnabled(True)
        self.llm_button.setEnabled(bool(self._last_imported))
        if self.auto_llm.isChecked() and self._last_imported:
            self._run_llm_review()

    def _open_main_window_panel(self, handler_name: str) -> None:
        window = self.window()
        if window is None:
            return
        handler = getattr(window, handler_name, None)
        if callable(handler):
            handler()

    def _run_llm_review(self) -> None:
        if not self._last_imported:
            QMessageBox.information(
                self,
                "No Scenes",
                "Import chats first to generate scenes before sending them to the LLM.",
            )
            return
        dialog = LLMSummariseDialog(
            bridge=self.bridge,
            scenes=self._last_imported,
            instructions=self.instructions_edit.toPlainText().strip(),
            lines_per_chunk=self.chunk_spin.value(),
            store=self.store,
            parent=self,
        )
        dialog.exec()


class STPersonaImportWidget(QWidget):
    """Guided SillyTavern persona importer."""

    def __init__(self, bridge: ServerBridge, *, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.bridge = bridge
        self._raw_payload: Any = None
        self._personas: List[Dict[str, Any]] = []
        self._loaded_path: Optional[Path] = None

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Load a SillyTavern persona export to register characters and profiles."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        self.load_button = QPushButton("Load Persona Export…")
        self.load_button.clicked.connect(self._load_file)
        row.addWidget(self.load_button)
        self.path_label = QLabel("No file selected.")
        self.path_label.setWordWrap(True)
        row.addWidget(self.path_label, 1)
        layout.addLayout(row)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        self.import_button = QPushButton("Import Personas")
        self.import_button.clicked.connect(self._import_payload)
        self.import_button.setEnabled(False)
        buttons.addWidget(self.import_button)

        self.open_persona_button = QPushButton("Open Persona Panel")
        self.open_persona_button.clicked.connect(
            lambda: self._open_main_window_panel("open_player_persona_panel")
        )
        self.open_persona_button.setEnabled(False)
        buttons.addWidget(self.open_persona_button)

        self.open_characters_button = QPushButton("Open Characters Panel")
        self.open_characters_button.clicked.connect(
            lambda: self._open_main_window_panel("open_characters_panel")
        )
        self.open_characters_button.setEnabled(False)
        buttons.addWidget(self.open_characters_button)

        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Persona Export",
            "",
            "JSON Files (*.json *.jsonl);;All Files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            payload = json.loads(text)
        except Exception as exc:
            QMessageBox.warning(
                self, "Load Failed", f"Unable to load persona export:\n{exc}"
            )
            return
        personas = [entry for entry in iter_persona_payloads(payload)]
        if not personas:
            QMessageBox.warning(
                self,
                "No Personas Found",
                "The selected file does not contain persona entries.",
            )
            return
        self._raw_payload = payload
        self._personas = personas
        self._loaded_path = Path(path)
        self._refresh_preview()
        self.import_button.setEnabled(True)
        self.status_label.setText("Persona payload loaded. Review and import.")

    def _refresh_preview(self) -> None:
        self.list_widget.clear()
        if not self._personas:
            return
        for record in self._personas:
            name = (
                record.get("display_name")
                or record.get("name")
                or record.get("title")
                or record.get("id")
                or "Persona"
            )
            role = record.get("role") or record.get("persona_role") or "npc"
            tags = record.get("tags") or record.get("category")
            tags_text = _preview_text(tags)
            item = QListWidgetItem(f"{name} — role: {role} — tags: {tags_text}")
            self.list_widget.addItem(item)

    def _import_payload(self) -> None:
        if self._raw_payload is None:
            QMessageBox.information(self, "No Payload", "Load a persona export first.")
            return
        self.import_button.setEnabled(False)
        result = self.bridge.post_json(
            "/st/import",
            {"type": "personas", "data": self._raw_payload},
            timeout=20.0,
            default=None,
        )
        self.import_button.setEnabled(True)
        if not isinstance(result, dict) or not result.get("ok"):
            detail = ""
            if isinstance(result, dict):
                detail = str(result.get("data") or result.get("error") or "")
            QMessageBox.warning(
                self, "Import Failed", f"Server rejected the payload.\n{detail}"
            )
            self.status_label.setText("Import failed.")
            return
        data = result.get("data") or {}
        count = data.get("imported") or 0
        errors = data.get("errors") or []
        summary = f"Imported {count} persona(s)."
        if errors:
            summary += f" {len(errors)} entry/entries reported errors."
        self.status_label.setText(summary)
        self.open_persona_button.setEnabled(True)
        self.open_characters_button.setEnabled(True)

    def _open_main_window_panel(self, handler_name: str) -> None:
        window = self.window()
        if window is None:
            return
        handler = getattr(window, handler_name, None)
        if callable(handler):
            handler()


class STWorldImportWidget(QWidget):
    """Guided SillyTavern world/lore importer."""

    def __init__(self, bridge: ServerBridge, *, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.bridge = bridge
        self._raw_payload: Any = None
        self._worlds: List[Tuple[str, Dict[str, Any]]] = []
        self._loaded_path: Optional[Path] = None

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Load a SillyTavern world or lore export to register setting data."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        self.load_button = QPushButton("Load World Export…")
        self.load_button.clicked.connect(self._load_file)
        row.addWidget(self.load_button)
        self.path_label = QLabel("No file selected.")
        self.path_label.setWordWrap(True)
        row.addWidget(self.path_label, 1)
        layout.addLayout(row)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        self.import_button = QPushButton("Import Worlds")
        self.import_button.clicked.connect(self._import_payload)
        self.import_button.setEnabled(False)
        buttons.addWidget(self.import_button)

        self.open_imports_button = QPushButton("Open Imports Panel")
        self.open_imports_button.clicked.connect(
            lambda: self._open_main_window_panel("open_imports_panel")
        )
        self.open_imports_button.setEnabled(False)
        buttons.addWidget(self.open_imports_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select World Export",
            "",
            "JSON Files (*.json *.jsonl);;All Files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            payload = json.loads(text)
        except Exception as exc:
            QMessageBox.warning(
                self, "Load Failed", f"Unable to load world export:\n{exc}"
            )
            return
        worlds = _iter_world_payloads(payload)
        if not worlds:
            QMessageBox.warning(
                self,
                "No Worlds Found",
                "The selected file does not contain world or lore entries.",
            )
            return
        self._raw_payload = payload
        self._worlds = worlds
        self._loaded_path = Path(path)
        self._refresh_preview()
        self.import_button.setEnabled(True)
        self.status_label.setText("World payload loaded. Review and import.")

    def _refresh_preview(self) -> None:
        self.list_widget.clear()
        for name, data in self._worlds:
            description = (
                data.get("description") or data.get("summary") or data.get("notes")
            )
            preview = _preview_text(description)
            item = QListWidgetItem(f"{name} — {preview}")
            self.list_widget.addItem(item)

    def _import_payload(self) -> None:
        if self._raw_payload is None:
            QMessageBox.information(self, "No Payload", "Load a world export first.")
            return
        self.import_button.setEnabled(False)
        result = self.bridge.post_json(
            "/st/import",
            {"type": "worlds", "data": self._raw_payload},
            timeout=20.0,
            default=None,
        )
        self.import_button.setEnabled(True)
        if not isinstance(result, dict) or not result.get("ok"):
            detail = ""
            if isinstance(result, dict):
                detail = str(result.get("data") or result.get("error") or "")
            QMessageBox.warning(
                self, "Import Failed", f"Server rejected the payload.\n{detail}"
            )
            self.status_label.setText("Import failed.")
            return
        data = result.get("data") or {}
        count = data.get("imported") or 0
        errors = data.get("errors") or []
        summary = f"Imported {count} world(s)."
        if errors:
            summary += f" {len(errors)} entry/entries reported errors."
        self.status_label.setText(summary)
        self.open_imports_button.setEnabled(True)

    def _open_main_window_panel(self, handler_name: str) -> None:
        window = self.window()
        if window is None:
            return
        handler = getattr(window, handler_name, None)
        if callable(handler):
            handler()


class RoleplayImportWidget(QWidget):
    """Guided roleplay transcript importer."""

    def __init__(self, bridge: ServerBridge, *, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.bridge = bridge
        self._loaded_path: Optional[Path] = None

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Load a roleplay transcript (text or JSON) and queue the roleplay importer."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        self.load_button = QPushButton("Load Transcript…")
        self.load_button.clicked.connect(self._load_file)
        row.addWidget(self.load_button)
        self.path_label = QLabel("No file selected.")
        self.path_label.setWordWrap(True)
        row.addWidget(self.path_label, 1)
        layout.addLayout(row)

        form = QFormLayout()
        self.title_edit = QLineEdit()
        form.addRow("Title:", self.title_edit)
        self.world_edit = QLineEdit()
        form.addRow("World:", self.world_edit)
        self.detail_combo = QComboBox()
        self.detail_combo.addItem("Low", "low")
        self.detail_combo.addItem("Medium", "medium")
        self.detail_combo.addItem("High", "high")
        self.detail_combo.setCurrentIndex(1)
        form.addRow("Detail Level:", self.detail_combo)
        layout.addLayout(form)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("Paste or load the roleplay transcript here…")
        self.text_edit.setMinimumHeight(200)
        layout.addWidget(self.text_edit, 1)

        self.analysis_label = QLabel("")
        self.analysis_label.setWordWrap(True)
        self.analysis_label.setObjectName("roleplay-analysis-label")
        layout.addWidget(self.analysis_label)

        buttons = QHBoxLayout()
        self.import_button = QPushButton("Import Transcript")
        self.import_button.clicked.connect(self._import_payload)
        buttons.addWidget(self.import_button)
        self.open_scenes_button = QPushButton("Open Scenes Panel")
        self.open_scenes_button.clicked.connect(
            lambda: self._open_main_window_panel("open_scenes_panel")
        )
        self.open_scenes_button.setEnabled(False)
        buttons.addWidget(self.open_scenes_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._last_speakers: List[str] = []

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Roleplay Transcript",
            "",
            "Text/JSON Files (*.txt *.json *.jsonl);;All Files (*)",
        )
        if not path:
            return
        path_obj = Path(path)
        try:
            text = path_obj.read_text(encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(
                self, "Load Failed", f"Unable to read transcript:\n{exc}"
            )
            return

        transcript = text
        meta: Dict[str, Any] = {}
        if path_obj.suffix.lower() in {".json", ".jsonl"}:
            extracted = self._extract_transcript_from_json(text)
            if extracted:
                transcript, meta = extracted
                self.status_label.setText("JSON transcript parsed successfully.")
            else:
                self.status_label.setText(
                    "JSON parsing failed; loaded transcript as plain text."
                )
        self.text_edit.setPlainText(transcript)
        if meta.get("title"):
            self.title_edit.setText(str(meta["title"]))
        if meta.get("world"):
            self.world_edit.setText(str(meta["world"]))
        detail = meta.get("detail_level") or meta.get("detailLevel")
        if detail:
            idx = self.detail_combo.findData(detail)
            if idx >= 0:
                self.detail_combo.setCurrentIndex(idx)
        self._loaded_path = path_obj
        preset_speakers = meta.get("speakers")
        self._update_analysis(transcript, preset_speakers=preset_speakers)
        self.status_label.setText(
            f"Loaded {path_obj.name} ({len(self.text_edit.toPlainText().splitlines())} lines)."
        )

    def _extract_transcript_from_json(
        self, raw: str
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            normalized = raw.strip()
            if not normalized:
                return None
            decoder = json.JSONDecoder()
            idx = 0
            length = len(normalized)
            transcripts: List[str] = []
            combined_meta: Dict[str, Any] = {}
            speaker_pool: set[str] = set()
            while idx < length:
                try:
                    obj, offset = decoder.raw_decode(normalized, idx)
                except json.JSONDecodeError:
                    break
                idx = offset
                while idx < length and normalized[idx].isspace():
                    idx += 1
                if isinstance(obj, dict):
                    text, meta = self._transcript_from_payload(obj)
                    if text:
                        transcripts.append(text)
                        for name in meta.get("speakers", []):
                            speaker_pool.add(name)
                    combined_meta.update(
                        {k: v for k, v in meta.items() if k != "speakers"}
                    )
            if transcripts:
                if speaker_pool:
                    combined_meta["speakers"] = sorted(speaker_pool)
                return ("\n\n".join(transcripts), combined_meta)
            return None
        if isinstance(payload, list):
            transcripts: List[str] = []
            combined_meta: Dict[str, Any] = {}
            speaker_pool: set[str] = set()
            for item in payload:
                if not isinstance(item, dict):
                    continue
                text, meta = self._transcript_from_payload(item)
                if text:
                    transcripts.append(text)
                    for name in meta.get("speakers", []):
                        speaker_pool.add(name)
                combined_meta.update({k: v for k, v in meta.items() if k != "speakers"})
            if transcripts:
                if speaker_pool:
                    combined_meta["speakers"] = sorted(speaker_pool)
                return ("\n\n".join(transcripts), combined_meta)
            return None
        if isinstance(payload, dict):
            text, meta = self._transcript_from_payload(payload)
            if text:
                speakers = meta.get("speakers")
                if speakers:
                    meta = dict(meta)
                    meta["speakers"] = sorted(set(speakers))
                return text, meta
        return None

    def _import_payload(self) -> None:
        transcript_raw = self.text_edit.toPlainText().strip()
        if not transcript_raw:
            QMessageBox.information(
                self, "No Transcript", "Paste or load a transcript before importing."
            )
            return
        transcript_clean = self._normalise_transcript(transcript_raw)
        if transcript_clean != transcript_raw:
            self.text_edit.setPlainText(transcript_clean)
        self._update_analysis(transcript_clean)
        payload: Dict[str, Any] = {
            "text": transcript_clean,
            "title": self.title_edit.text().strip() or None,
            "world": self.world_edit.text().strip() or None,
            "source": "studio.gui",
            "detail_level": self.detail_combo.currentData(),
            "blocking": True,
        }
        metadata: Dict[str, Any] = {}
        if self._loaded_path:
            metadata["source_path"] = str(self._loaded_path)
        if self._last_speakers:
            metadata["detected_speakers"] = self._last_speakers
        if metadata:
            payload["metadata"] = metadata
        self.import_button.setEnabled(False)
        result = self.bridge.post_json(
            "/api/imports/roleplay", payload, timeout=60.0, default=None
        )
        self.import_button.setEnabled(True)
        if not isinstance(result, dict) or not result.get("ok"):
            detail = ""
            if isinstance(result, dict):
                detail = str(result.get("data") or result.get("error") or "")
            QMessageBox.warning(
                self, "Import Failed", f"Server rejected the transcript.\n{detail}"
            )
            self.status_label.setText("Import failed.")
            return
        data = result.get("data") or {}
        scene = data.get("scene") or {}
        scene_uid = scene.get("id") or data.get("scene_uid")
        message = "Transcript imported."
        if scene_uid:
            message += f" Scene UID: {scene_uid}"
        preview_path = data.get("preview_path")
        if preview_path:
            message += f" Preview: {preview_path}"
        self.status_label.setText(message)
        self.open_scenes_button.setEnabled(True)

    def _open_main_window_panel(self, handler_name: str) -> None:
        window = self.window()
        if window is None:
            return
        handler = getattr(window, handler_name, None)
        if callable(handler):
            handler()

    def _normalise_transcript(self, text: str) -> str:
        cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
        cleaned = re.sub(r"\[[^\]]*\]\((https?://[^)]+)\)", r"\1", cleaned)
        cleaned = re.sub(r"\r\n?", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _guess_speakers(self, text: str) -> List[str]:
        speakers: List[str] = []
        seen: set[str] = set()
        pattern = re.compile(r"^\s*([A-Za-z0-9 _'\-]{2,40})\s*[:：]\s+")
        for line in text.splitlines():
            match = pattern.match(line)
            if not match:
                continue
            name = match.group(1).strip()
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            speakers.append(name)
            if len(speakers) >= 8:
                break
        return speakers

    def _update_analysis(
        self, text: str, *, preset_speakers: Optional[List[str]] = None
    ) -> None:
        cleaned = self._normalise_transcript(text)
        speakers = (
            list(preset_speakers) if preset_speakers else self._guess_speakers(cleaned)
        )
        words = len(cleaned.split())
        lines = len(cleaned.splitlines())
        summary = f"Approx. {words} word(s), {lines} line(s)."
        if speakers:
            summary += " Detected speakers: " + ", ".join(speakers)
            if len(speakers) >= 8:
                summary += "…"
        else:
            summary += " (No speaker prefixes detected.)"
        self.analysis_label.setText(summary)
        self._last_speakers = speakers

    def _transcript_from_payload(
        self, payload: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        meta: Dict[str, Any] = {}
        speaker_names: List[str] = []

        def _speaker_name(data: Dict[str, Any]) -> str:
            if bool(data.get("is_user")):
                return "You"
            for key in (
                "name",
                "character_name",
                "character",
                "display_name",
                "role",
            ):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return "Narrator"

        def _merge_child_data(child_text: str, child_meta: Dict[str, Any]) -> None:
            if child_text:
                collected.append(child_text)
            for entry in child_meta.get("speakers", []):
                if entry not in speaker_names:
                    speaker_names.append(entry)
            for key in ("title", "world", "detail_level", "detailLevel"):
                if key in child_meta and key not in meta:
                    meta[key] = child_meta[key]

        if "mes" in payload:
            speaker = _speaker_name(payload)
            text = str(payload.get("mes") or "")
            cleaned = self._normalise_transcript(text)
            if cleaned:
                if speaker not in speaker_names:
                    speaker_names.append(speaker)
                meta["speakers"] = speaker_names.copy()
                return f"{speaker}: {cleaned}", meta

        transcript = str(
            payload.get("text")
            or payload.get("transcript")
            or payload.get("content")
            or ""
        )
        collected: List[str] = []
        if not transcript and isinstance(payload.get("lines"), list):
            for line in payload["lines"]:
                if not isinstance(line, dict):
                    continue
                child_text, child_meta = self._transcript_from_payload(line)
                _merge_child_data(child_text, child_meta)
            transcript = "\n".join(filter(None, collected))
        if not transcript and isinstance(payload.get("messages"), list):
            for entry in payload["messages"]:
                if not isinstance(entry, dict):
                    continue
                child_text, child_meta = self._transcript_from_payload(entry)
                _merge_child_data(child_text, child_meta)
            transcript = "\n".join(filter(None, collected))
        if not transcript and isinstance(payload.get("entries"), list):
            for entry in payload["entries"]:
                if not isinstance(entry, dict):
                    continue
                child_text, child_meta = self._transcript_from_payload(entry)
                _merge_child_data(child_text, child_meta)
            transcript = "\n".join(filter(None, collected))

        for key in ("title", "world", "detail_level", "detailLevel"):
            if payload.get(key):
                meta[key] = payload[key]
        if speaker_names:
            meta["speakers"] = speaker_names.copy()
        return self._normalise_transcript(transcript), meta


class LLMSummariseDialog(QDialog):
    """Collect LLM parameters and run summaries over imported scenes."""

    def __init__(
        self,
        *,
        bridge: ServerBridge,
        scenes: List[Dict[str, Any]],
        instructions: str,
        lines_per_chunk: int,
        store: SceneStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.scenes = scenes
        self.lines_per_chunk = max(0, lines_per_chunk)
        self.store = store
        self.setWindowTitle("LLM Scene Review")

        layout = QVBoxLayout(self)
        desc = QLabel(
            "Select a provider/model and send the imported scenes through `/api/llm/test-call`.\n"
            "Chunks respect the chosen line limit to keep prompts manageable."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider:", self.provider_combo)
        self.model_combo = QComboBox()
        form.addRow("Model:", self.model_combo)
        self.prompt_combo = QComboBox()
        self.prompt_combo.addItem("Custom instructions", "")
        for label, template in PROMPT_LIBRARY:
            self.prompt_combo.addItem(label, template)
        self.prompt_combo.currentIndexChanged.connect(self._apply_prompt_template)
        form.addRow("Prompt template:", self.prompt_combo)
        layout.addLayout(form)

        self.instructions_edit = QPlainTextEdit()
        base_instructions = instructions or (
            "Summarise the conversation, then list potential scene edits in bullet form."
        )
        self.instructions_edit.setPlainText(base_instructions)
        self.instructions_edit.setFixedHeight(120)
        layout.addWidget(self.instructions_edit)

        self.scene_list = QListWidget()
        for scene in self.scenes:
            title = scene.get("title") or scene.get("id") or "Scene"
            item = QListWidgetItem(title)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.scene_list.addItem(item)
        layout.addWidget(self.scene_list, 1)

        self.result_edit = QPlainTextEdit()
        self.result_edit.setReadOnly(True)
        layout.addWidget(self.result_edit, 2)

        self.run_button = QPushButton("Run Summaries")
        self.run_button.clicked.connect(self._run)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        button_box.addButton(self.run_button, QDialogButtonBox.ActionRole)
        layout.addWidget(button_box)

        self._load_registry()

    def _load_registry(self) -> None:
        self.provider_combo.clear()
        result = self.bridge.get_json("/api/llm/registry", timeout=6.0, default=None)
        providers: List[Dict[str, Any]] = []
        if isinstance(result, dict) and result.get("ok"):
            data = result.get("data")
            if isinstance(data, dict):
                provider_list = data.get("providers")
                if isinstance(provider_list, list):
                    providers = [
                        entry for entry in provider_list if isinstance(entry, dict)
                    ]
        if providers:
            for entry in providers:
                name = entry.get("name") or entry.get("adapter")
                if not name:
                    continue
                self.provider_combo.addItem(str(name), entry)
        else:
            self.provider_combo.addItem("stub", {"name": "stub", "models": []})
        self._on_provider_changed(self.provider_combo.currentIndex())

    def _on_provider_changed(self, index: int) -> None:
        self.model_combo.clear()
        entry = self.provider_combo.itemData(index)
        if not isinstance(entry, dict):
            self.model_combo.addItem("default", "default")
            return
        models = entry.get("models") or []
        if not models:
            self.model_combo.addItem("default", "default")
            return
        for model in models:
            if not isinstance(model, dict):
                continue
            label = model.get("label") or model.get("id")
            model_id = model.get("id")
            if model_id:
                self.model_combo.addItem(str(label), str(model_id))

    def _apply_prompt_template(self, index: int) -> None:
        template = self.prompt_combo.itemData(index)
        if isinstance(template, str) and template:
            self.instructions_edit.setPlainText(template)

    def _selected_scenes(self) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        for row in range(self.scene_list.count()):
            item = self.scene_list.item(row)
            if item and item.checkState() == Qt.Checked:
                selected.append(self.scenes[row])
        return selected

    def _run(self) -> None:
        chosen = self._selected_scenes()
        if not chosen:
            QMessageBox.information(
                self, "No Scenes Selected", "Select at least one scene to analyse."
            )
            return
        provider_entry = self.provider_combo.currentData()
        registry_id = ""
        if isinstance(provider_entry, dict):
            registry_id = str(
                provider_entry.get("name") or provider_entry.get("adapter") or ""
            ).strip()
        if not registry_id:
            registry_id = self.provider_combo.currentText().strip()
        model_id = self.model_combo.currentData()
        if not isinstance(model_id, str) or not model_id:
            model_id = self.model_combo.currentText()
        instructions = self.instructions_edit.toPlainText().strip() or (
            "Summarise the scene and highlight issues."
        )

        self.run_button.setEnabled(False)
        self.result_edit.clear()
        record_batches: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for scene in chosen:
            title = scene.get("title") or scene.get("id") or "Scene"
            dialogue_text = _format_dialogue(scene)
            lines = dialogue_text.splitlines()
            chunks = list(_chunk_lines(lines, self.lines_per_chunk))
            for index, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                label = f"{title} (chunk {index + 1})"
                payload = {
                    "registry_id": registry_id,
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": f"{label}\n\n{chunk}"},
                    ],
                }
                result = self.bridge.post_json(
                    "/api/llm/test-call",
                    payload,
                    timeout=45.0,
                    default=None,
                )
                if not isinstance(result, dict) or not result.get("ok"):
                    detail = ""
                    status = result.get("status") if isinstance(result, dict) else None
                    data = result.get("data") if isinstance(result, dict) else None
                    if isinstance(data, dict):
                        detail = json.dumps(data, indent=2)
                    elif isinstance(result, dict):
                        detail = str(result.get("error") or data or "")
                    self.result_edit.appendPlainText(
                        f"[{label}] Failed (status={status}): {detail}\n"
                    )
                    continue
                payload_data = result.get("data") or {}
                reply = payload_data.get("reply") or "(no reply)"
                self.result_edit.appendPlainText(f"[{label}]\n{reply}\n")
                scene_id = scene.get("id") or scene.get("scene_uid")
                if scene_id:
                    record_batches[scene_id].append(
                        {
                            "timestamp": time.time(),
                            "provider": registry_id,
                            "model": model_id,
                            "instructions": instructions,
                            "chunk_index": index + 1,
                            "chunk_total": len(chunks),
                            "label": label,
                            "reply": reply,
                        }
                    )
        if record_batches:
            self._persist_reviews(record_batches)
            self.result_edit.appendPlainText("\nSaved analysis to scene metadata.\n")
        self.run_button.setEnabled(True)

    def _persist_reviews(self, batches: Dict[str, List[Dict[str, Any]]]) -> None:
        if not self.store:
            return
        for scene_id, entries in batches.items():
            if not entries:
                continue
            scene_payload = self.store.load(scene_id)
            if not scene_payload:
                continue
            analysis = scene_payload.setdefault("analysis", {})
            reviews = analysis.setdefault("llm_reviews", [])
            reviews.extend(entries)
            self.store.save(scene_id, scene_payload)
