from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDockWidget, QFileDialog,
                               QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QTextEdit, QVBoxLayout, QWidget)

from comfyvn.gui.services.server_bridge import ServerBridge

LOGGER = logging.getLogger(__name__)


class PlayerPersonaPanel(QDockWidget):
    """Dockable panel for managing personas, characters, and quick pipeline actions."""

    def __init__(
        self,
        bridge: Optional[ServerBridge] = None,
        parent: Optional[QWidget] = None,
        *,
        open_sprite_manager: Optional[Callable[[], None]] = None,
        open_asset_manager: Optional[Callable[[], None]] = None,
        open_playground: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__("Player Persona Manager", parent)
        self.bridge = bridge or ServerBridge()
        self._roster: Dict[str, Any] = {"characters": [], "personas": [], "active": {}}
        self._open_sprite_cb = open_sprite_manager
        self._open_asset_cb = open_asset_manager
        self._open_playground_cb = open_playground

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        controls = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh Roster", root)
        self.btn_import = QPushButton("Import Character…", root)
        self.btn_reload = QPushButton("Reload State", root)
        controls.addWidget(self.btn_refresh)
        controls.addWidget(self.btn_import)
        controls.addWidget(self.btn_reload)
        controls.addStretch(1)
        layout.addLayout(controls)

        actions = QHBoxLayout()
        self.btn_process = QPushButton("Process Persona", root)
        self.btn_open_sprites = QPushButton("Sprite Manager", root)
        self.btn_open_assets = QPushButton("Asset Browser", root)
        self.btn_playground = QPushButton("Playground Mode", root)
        actions.addWidget(self.btn_process)
        actions.addWidget(self.btn_open_sprites)
        actions.addWidget(self.btn_open_assets)
        actions.addWidget(self.btn_playground)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.active_label = QLabel("Active persona: <i>none</i>", root)
        self.active_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.active_label)

        lists_row = QHBoxLayout()
        char_column = QVBoxLayout()
        char_column.addWidget(QLabel("Characters", root))
        self.character_list = QListWidget(root)
        self.character_list.setSelectionMode(QListWidget.SingleSelection)
        char_column.addWidget(self.character_list, 1)
        self.btn_set_active_character = QPushButton("Set Active Character", root)
        char_column.addWidget(self.btn_set_active_character)
        lists_row.addLayout(char_column, 1)

        persona_column = QVBoxLayout()
        persona_column.addWidget(QLabel("Personas", root))
        self.persona_list = QListWidget(root)
        self.persona_list.setSelectionMode(QListWidget.SingleSelection)
        persona_column.addWidget(self.persona_list, 1)
        self.btn_set_active_persona = QPushButton("Set Active Persona", root)
        persona_column.addWidget(self.btn_set_active_persona)
        persona_column.addWidget(QLabel("Detail Level", root))
        self.detail_combo = QComboBox(root)
        self.detail_combo.addItem("Low", "low")
        self.detail_combo.addItem("Medium", "medium")
        self.detail_combo.addItem("High", "high")
        self.detail_combo.setCurrentIndex(1)
        persona_column.addWidget(self.detail_combo)
        lists_row.addLayout(persona_column, 1)
        layout.addLayout(lists_row, 1)

        self.details = QTextEdit(root)
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Persona details will appear here.")
        layout.addWidget(self.details, 1)

        root.setLayout(layout)
        self.setWidget(root)

        # Signals
        self.btn_refresh.clicked.connect(self._refresh_roster)
        self.btn_reload.clicked.connect(self._reload_state)
        self.btn_import.clicked.connect(self._import_character)
        self.btn_set_active_persona.clicked.connect(self._activate_selected_persona)
        self.btn_set_active_character.clicked.connect(self._activate_selected_character)
        self.btn_process.clicked.connect(self._process_persona)
        self.btn_open_sprites.clicked.connect(self._open_sprite_manager)
        self.btn_open_assets.clicked.connect(self._open_asset_manager)
        self.btn_playground.clicked.connect(self._enter_playground_mode)

        self.character_list.currentItemChanged.connect(
            lambda *_: self._populate_personas()
        )
        self.persona_list.currentItemChanged.connect(self._update_details)

        self._refresh_roster()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_payload(self, result: Any, context: str) -> Optional[Dict[str, Any]]:
        if not isinstance(result, dict) or not result.get("ok"):
            error = (
                (result or {}).get("error")
                if isinstance(result, dict)
                else "unknown error"
            )
            QMessageBox.warning(self, context.capitalize(), f"Request failed: {error}")
            return None
        payload = result.get("data")
        if not isinstance(payload, dict):
            QMessageBox.warning(
                self, context.capitalize(), "Unexpected server response format."
            )
            return None
        return payload

    def _refresh_roster(self) -> None:
        payload = self._extract_payload(
            self.bridge.get_json("/player/roster", timeout=8.0, default=None), "roster"
        )
        if payload is None:
            return
        self._roster = {
            "characters": payload.get("characters") or [],
            "personas": payload.get("personas") or [],
            "active": payload.get("active") or {},
        }
        self._populate_characters()
        self._populate_personas()
        self._update_active_label()
        self._update_details()

    def _reload_state(self) -> None:
        payload = self._extract_payload(
            self.bridge.post_json("/player/refresh", {}, timeout=8.0, default=None),
            "reload",
        )
        if payload is None:
            return
        self._roster = {
            "characters": payload.get("characters") or [],
            "personas": payload.get("personas") or [],
            "active": payload.get("state") or {},
        }
        self._populate_characters()
        self._populate_personas()
        self._update_active_label()
        self._update_details()

    def _populate_characters(self) -> None:
        self.character_list.blockSignals(True)
        current_id = self._selected_character_id()
        self.character_list.clear()
        active_id = (self._roster.get("active") or {}).get("character_id")
        for character in self._roster.get("characters", []):
            cid = character.get("id") or character.get("name")
            if not cid:
                continue
            label = character.get("display_name") or character.get("name") or cid
            if cid == active_id:
                label = f"{label}  — ACTIVE"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, cid)
            self.character_list.addItem(item)
            if cid == current_id:
                self.character_list.setCurrentItem(item)
        self.character_list.blockSignals(False)
        if self.character_list.count() and not self.character_list.currentItem():
            self.character_list.setCurrentRow(0)

    def _populate_personas(self) -> None:
        selected_character = self._selected_character_id()
        active_persona = (self._roster.get("active") or {}).get("persona_id")
        self.persona_list.blockSignals(True)
        self.persona_list.clear()
        for persona in self._roster.get("personas", []):
            persona_id = persona.get("id") or persona.get("name")
            if not persona_id:
                continue
            if selected_character and persona.get("character_id") not in {
                None,
                selected_character,
            }:
                continue
            label = persona.get("display_name") or persona.get("name") or persona_id
            if persona_id == active_persona:
                label = f"{label}  — ACTIVE"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, persona_id)
            item.setData(Qt.UserRole + 1, persona)
            self.persona_list.addItem(item)
        self.persona_list.blockSignals(False)
        if self.persona_list.count() and not self.persona_list.currentItem():
            self.persona_list.setCurrentRow(0)

    def _update_active_label(self) -> None:
        state = self._roster.get("active") or {}
        persona_id = state.get("persona_id") or "<i>none</i>"
        character_id = state.get("character_id") or "—"
        mode = state.get("mode") or "vn"
        label = f"Active persona: <b>{persona_id}</b> (character: {character_id}, mode: {mode})"
        self.active_label.setText(label)
        if mode == "playground":
            self.btn_playground.setText("Return to VN Mode")
        else:
            self.btn_playground.setText("Playground Mode")

    def _update_details(self) -> None:
        item = self.persona_list.currentItem()
        if not item:
            self.details.clear()
            return
        persona = item.data(Qt.UserRole + 1) or {}
        detail_level = (
            persona.get("detail_level") if isinstance(persona, dict) else None
        )
        if isinstance(detail_level, str):
            idx = self.detail_combo.findData(detail_level.lower())
            if idx != -1:
                self.detail_combo.setCurrentIndex(idx)
        try:
            pretty = json.dumps(persona, indent=2, ensure_ascii=False)
        except Exception:
            pretty = str(persona)
        self.details.setPlainText(pretty)

    def _selected_character_id(self) -> Optional[str]:
        item = self.character_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _selected_persona_id(self) -> Optional[str]:
        item = self.persona_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _activate_selected_persona(self) -> None:
        persona_id = self._selected_persona_id()
        if not persona_id:
            QMessageBox.information(self, "Persona", "Select a persona to activate.")
            return
        payload = {
            "persona": persona_id,
            "detail_level": self.detail_combo.currentData(),
        }
        character_id = self._selected_character_id()
        if character_id:
            payload["character"] = character_id
        if (
            self._extract_payload(
                self.bridge.post_json(
                    "/player/select", payload, timeout=5.0, default=None
                ),
                "persona activation",
            )
            is None
        ):
            return
        self._refresh_roster()

    def _activate_selected_character(self) -> None:
        character_id = self._selected_character_id()
        if not character_id:
            QMessageBox.information(
                self, "Character", "Select a character to activate."
            )
            return
        payload = {
            "character": character_id,
            "detail_level": self.detail_combo.currentData(),
        }
        if (
            self._extract_payload(
                self.bridge.post_json(
                    "/player/select", payload, timeout=5.0, default=None
                ),
                "character activation",
            )
            is None
        ):
            return
        self._refresh_roster()

    def _import_character(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Character JSON", "", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            QMessageBox.critical(self, "Import", f"Failed to read file:\n{exc}")
            return

        body = {"character": payload, "auto_select": True}
        if (
            self._extract_payload(
                self.bridge.post_json(
                    "/player/import", body, timeout=10.0, default=None
                ),
                "import",
            )
            is None
        ):
            return
        QMessageBox.information(self, "Import", "Character imported successfully.")
        self._refresh_roster()

    def _process_persona(self) -> None:
        persona_id = self._selected_persona_id()
        if not persona_id:
            QMessageBox.information(self, "Process", "Select a persona first.")
            return
        payload = {
            "persona": persona_id,
            "detail_level": self.detail_combo.currentData(),
            "export": True,
        }
        data = self._extract_payload(
            self.bridge.post_json(
                "/player/process", payload, timeout=10.0, default=None
            ),
            "process",
        )
        if data is None:
            return
        try:
            pretty = json.dumps(data, indent=2, ensure_ascii=False)
        except Exception:
            pretty = str(data)
        self.details.setPlainText(pretty)
        QMessageBox.information(self, "Process", "Persona processed. Summary updated.")
        self._refresh_roster()

    def _open_sprite_manager(self) -> None:
        if callable(self._open_sprite_cb):
            self._open_sprite_cb()

    def _open_asset_manager(self) -> None:
        if callable(self._open_asset_cb):
            self._open_asset_cb()

    def _enter_playground_mode(self) -> None:
        state = self._extract_payload(
            self.bridge.get_json("/player/state", timeout=5.0, default=None), "state"
        )
        persona_id = state.get("persona_id") if state else None
        payload: Dict[str, Any] = {
            "mode": "playground",
            "detail_level": self.detail_combo.currentData(),
        }
        selected_persona = self._selected_persona_id()
        if selected_persona:
            payload["persona"] = selected_persona
        elif persona_id:
            payload["persona"] = persona_id
        if (
            self._extract_payload(
                self.bridge.post_json(
                    "/player/select", payload, timeout=5.0, default=None
                ),
                "playground mode",
            )
            is None
        ):
            return
        if callable(self._open_playground_cb):
            self._open_playground_cb()
        self._refresh_roster()


__all__ = ["PlayerPersonaPanel"]
