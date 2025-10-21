from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Optional

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.preview.presentation_preview import PresentationPlanPreview
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.presentation.directives import PresentationNode, SceneState

LOGGER = logging.getLogger(__name__)


class ScenesView(QWidget):
    """
    Read-only browser for scene records fetched from the Studio REST API.

    Displays a list of scenes on the left and a JSON inspector on the right.
    Falls back to mock data if the backend responds with 404 so the UI remains
    functional when the endpoint has not been provisioned yet.
    """

    def __init__(
        self,
        api_client: Optional[ServerBridge] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.api = api_client or ServerBridge()
        self._items: list[dict[str, Any]] = []

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)

        self.detail = QTextEdit(self)
        self.detail.setObjectName("scenesDetailInspector")
        self.detail.setReadOnly(True)
        self.detail.setLineWrapMode(QTextEdit.NoWrap)

        self.plan_preview = PresentationPlanPreview(parent=self)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

        refresh_button = QPushButton("Refresh", self)
        refresh_button.clicked.connect(self.refresh)
        self._refresh_button = refresh_button

        actions_row = QHBoxLayout()
        actions_row.addStretch(1)
        actions_row.addWidget(refresh_button)

        layout = QVBoxLayout(self)
        layout.addLayout(actions_row)

        split_row = QHBoxLayout()
        split_row.addWidget(self.list_widget, 1)

        detail_column = QVBoxLayout()
        detail_column.addWidget(self.detail, 1)
        detail_column.addWidget(self.plan_preview, 1)
        split_row.addLayout(detail_column, 2)

        layout.addLayout(split_row, 1)
        layout.addWidget(self.status_label)

        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Reload the list from the backend (or fallback)."""
        self._refresh_button.setEnabled(False)
        try:
            items, source = self._load_items()
        finally:
            self._refresh_button.setEnabled(True)

        self._items = items
        self.list_widget.clear()

        for index, item in enumerate(items):
            label = self._format_label(item, index)
            widget_item = QListWidgetItem(label)
            widget_item.setData(Qt.UserRole, item)
            self.list_widget.addItem(widget_item)

        if items:
            self.list_widget.setCurrentRow(0)
            self.status_label.setText(f"Loaded {len(items)} scene(s) from {source}.")
        else:
            self.detail.setPlainText("No scenes available.")
            self.status_label.setText("No scenes available.")
            self.plan_preview.show_idle(
                "Select a scene to compute presentation directives."
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_items(self) -> tuple[list[dict[str, Any]], str]:
        """Fetch scenes from REST API, falling back to mock data."""
        try:
            response = self.api.get_json("/api/scenes", timeout=4.0, default=None)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("ScenesView API error: %s", exc)
            return self._mock_items(), "mock data"

        if not isinstance(response, dict):
            return self._mock_items(), "mock data"

        status = response.get("status")
        if status == 404:
            return self._mock_items(), "mock data"

        if response.get("ok"):
            payload = response.get("data")
        else:
            payload = response.get("data")
            if status and status >= 500:
                LOGGER.warning("Scenes endpoint error status=%s", status)

        items = self._extract_items(payload or response)
        if items is None:
            return [], "server"
        return items, "server"

    def _extract_items(self, payload: Any) -> Optional[list[dict[str, Any]]]:
        """
        Normalise assorted payload structures into a list of dict rows.
        Accepts bare lists, or dictionaries containing `items` / `data`.
        """
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "data", "results", "rows", "scenes"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            # Some APIs might return a dict keyed by ids.
            values = list(payload.values())
            if values and all(isinstance(it, dict) for it in values):
                return [it for it in values if isinstance(it, dict)]
        return None

    def _mock_items(self) -> list[dict[str, Any]]:
        """Local fallback payload when the endpoint is unavailable."""
        return [
            {
                "id": "scene-prologue",
                "title": "Prologue",
                "summary": "Establishes the world and key characters.",
                "status": "draft",
            },
            {
                "id": "scene-market",
                "title": "Morning at the Bazaar",
                "summary": "Player meets the mentor character.",
                "location": "Old Town Market",
            },
            {
                "id": "scene-confrontation",
                "title": "Courtyard Confrontation",
                "summary": "First major branching choice for the player.",
                "status": "storyboard",
            },
        ]

    def _format_label(self, item: dict[str, Any], index: int) -> str:
        title = (
            str(item.get("title"))
            or str(item.get("name"))
            or str(item.get("id"))
            or f"Scene {index + 1}"
        )
        scene_id = item.get("id")
        if scene_id and scene_id != title:
            return f"{title} ({scene_id})"
        return title

    def _on_selection_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._items):
            self.detail.setPlainText("Select a scene to inspect its JSON payload.")
            self.plan_preview.show_idle(
                "Select a scene to compute presentation directives."
            )
            return
        item = self._items[index]
        serialized = json.dumps(item, indent=2, sort_keys=True)
        self.detail.setPlainText(serialized)
        self._update_plan_preview(item)

    def _update_plan_preview(self, scene: dict[str, Any]) -> None:
        components = self._extract_plan_components(scene)
        if not components:
            self.plan_preview.show_idle("No directive data available for this scene.")
            return
        scene_state, node = components
        self.plan_preview.update_plan(scene_state, node)

    def _extract_plan_components(
        self, scene: dict[str, Any]
    ) -> Optional[tuple[SceneState, PresentationNode]]:
        scene_id = self._coalesce_scene_id(scene)
        presentation = self._first_dict(
            scene.get("presentation"),
            self._nested_dict(scene, ("meta", "presentation")),
            self._nested_dict(scene, ("state", "presentation")),
        )

        raw_characters = self._first_list(
            (presentation or {}).get("characters"),
            scene.get("characters"),
            scene.get("cast"),
            self._nested_list(scene, ("state", "characters")),
        )
        character_payloads = self._normalise_characters(raw_characters)

        camera_payload = self._first_dict(
            (presentation or {}).get("camera"),
            scene.get("camera"),
            self._nested_dict(scene, ("state", "camera")),
        )
        timing_payload = self._first_dict(
            (presentation or {}).get("timing"),
            scene.get("timing"),
            self._nested_dict(scene, ("state", "timing")),
        )
        ambient_payload = (
            self._first_list(
                (presentation or {}).get("ambient_sfx"),
                scene.get("ambient_sfx"),
                scene.get("ambient"),
            )
            or []
        )

        scene_state_payload: dict[str, Any] = {
            "scene_id": scene_id,
            "characters": character_payloads,
            "camera": camera_payload or None,
            "timing": timing_payload or None,
            "ambient_sfx": ambient_payload,
        }

        nodes = self._first_list(
            scene.get("nodes"),
            (presentation or {}).get("nodes"),
            self._nested_list(scene, ("state", "nodes")),
        )
        node_payload = self._select_node_payload(scene_id, nodes)
        if node_payload is None:
            return None

        try:
            scene_state = SceneState.model_validate(scene_state_payload)
            node = PresentationNode.model_validate(node_payload)
        except ValidationError as exc:
            LOGGER.debug("Unable to build plan components: %s", exc)
            return None
        return scene_state, node

    def _select_node_payload(
        self, scene_id: str, nodes: Optional[Iterable[Any]]
    ) -> Optional[dict[str, Any]]:
        if not nodes:
            return None
        for raw in nodes:
            if not isinstance(raw, dict):
                continue
            node_type = str(raw.get("type") or "text").lower()
            if node_type not in {"text", "line", "dialogue", "action", "choice"}:
                if not raw.get("content"):
                    continue

            directives = (
                raw.get("directives")
                or self._nested_dict(raw, ("presentation", "directives"))
                or {}
            )
            speaker = (
                raw.get("speaker")
                or raw.get("character")
                or raw.get("actor")
                or self._nested_value(raw, ("content", "speaker"))
                or self._nested_value(raw, ("content", "character"))
            )

            return {
                "id": str(raw.get("id") or f"{scene_id}-node"),
                "type": raw.get("type") or "text",
                "speaker": speaker,
                "directives": directives,
                "meta": raw.get("meta") or {},
            }
        return None

    @staticmethod
    def _coalesce_scene_id(scene: dict[str, Any]) -> str:
        for key in ("id", "scene_id", "slug", "name", "title"):
            value = scene.get(key)
            if value:
                return str(value)
        return "scene-preview"

    @staticmethod
    def _normalise_characters(raw: Optional[Iterable[Any]]) -> list[dict[str, Any]]:
        if not raw:
            return []
        characters: list[dict[str, Any]] = []
        for entry in raw:
            if isinstance(entry, str):
                characters.append(
                    {
                        "id": entry,
                        "display_name": entry,
                        "slot": "center",
                    }
                )
                continue
            if not isinstance(entry, dict):
                continue
            candidate_id = (
                entry.get("id") or entry.get("character_id") or entry.get("name")
            )
            if not candidate_id:
                continue
            char_payload: dict[str, Any] = {
                "id": str(candidate_id),
                "display_name": entry.get("display_name") or entry.get("name"),
                "slot": entry.get("slot") or entry.get("position") or "center",
            }
            portrait = entry.get("portrait") or entry.get("portrait_asset")
            if portrait:
                char_payload["portrait"] = portrait
            default_expression = entry.get("default_expression") or entry.get(
                "expression"
            )
            if default_expression:
                char_payload["default_expression"] = default_expression
            default_pose = entry.get("default_pose") or entry.get("pose")
            if default_pose:
                char_payload["default_pose"] = default_pose
            tween_preset = entry.get("tween_preset") or entry.get("tween")
            if tween_preset:
                char_payload["tween_preset"] = tween_preset
            characters.append(char_payload)
        return characters

    @staticmethod
    def _first_list(*candidates: Any) -> Optional[list[Any]]:
        for candidate in candidates:
            if isinstance(candidate, list) and candidate:
                return candidate
        return None

    @staticmethod
    def _first_dict(*candidates: Any) -> Optional[dict[str, Any]]:
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate:
                return candidate
        return None

    @staticmethod
    def _nested_dict(container: Any, path: Iterable[str]) -> Optional[dict[str, Any]]:
        value = ScenesView._nested_value(container, path)
        return value if isinstance(value, dict) else None

    @staticmethod
    def _nested_list(container: Any, path: Iterable[str]) -> Optional[list[Any]]:
        value = ScenesView._nested_value(container, path)
        return value if isinstance(value, list) else None

    @staticmethod
    def _nested_value(container: Any, path: Iterable[str]) -> Any:
        current = container
        for segment in path:
            if not isinstance(current, dict):
                return None
            current = current.get(segment)
        return current
