from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from comfyvn.config.runtime_paths import data_dir
from comfyvn.core.memory_engine import remember_event

LOGGER = logging.getLogger(__name__)


class CharacterManager:
    """Lightweight registry for player and NPC character metadata."""

    def __init__(self, data_path: str | Path | None = None) -> None:
        self.data_path = Path(data_path) if data_path else data_dir("characters")
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.characters: Dict[str, Dict[str, Any]] = {}
        self._load_existing()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _character_path(self, character_id: str) -> Path:
        return self.data_path / f"{character_id}.json"

    def _load_existing(self) -> None:
        self.characters.clear()
        for file in self.data_path.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except Exception as exc:
                LOGGER.warning("Skipping character %s (invalid json): %s", file, exc)
                continue
            character_id = str(data.get("id") or file.stem)
            data.setdefault("id", character_id)
            data.setdefault("name", data.get("name") or character_id)
            data.setdefault("created_at", data.get("created_at") or time.time())
            self.characters[character_id] = data

    def _save_character(self, character_id: str, payload: Dict[str, Any]) -> None:
        path = self._character_path(character_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def reload(self) -> None:
        """Reload character metadata from disk."""
        self._load_existing()

    def list_characters(self) -> List[Dict[str, Any]]:
        """Return registered characters as shallow copies."""
        items: List[Dict[str, Any]] = []
        for character_id, data in sorted(self.characters.items()):
            entry = dict(data)
            entry.setdefault("id", character_id)
            items.append(entry)
        return items

    def get_character(self, character_id: str) -> Optional[Dict[str, Any]]:
        """Return a character record if present."""
        record = self.characters.get(character_id)
        return dict(record) if record else None

    def register_character(
        self, character_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create or update a character record."""
        character_id = str(character_id).strip()
        if not character_id:
            raise ValueError("character_id is required")
        record = dict(payload or {})
        record["id"] = character_id
        record.setdefault("name", record.get("display_name") or character_id)
        record.setdefault("display_name", record["name"])
        record.setdefault("tags", record.get("tags") or [])
        record.setdefault("avatars", record.get("avatars") or [])
        record.setdefault("created_at", record.get("created_at") or time.time())
        record.setdefault("updated_at", time.time())
        self.characters[character_id] = record
        self._save_character(character_id, record)
        remember_event(
            "character.register", {"id": character_id, "name": record.get("name")}
        )
        return dict(record)

    def update_character(
        self, character_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge metadata into an existing character."""
        existing = self.characters.get(character_id)
        if not existing:
            raise KeyError(f"character '{character_id}' not found")
        merged = dict(existing)
        merged.update(payload or {})
        merged["id"] = character_id
        merged["updated_at"] = time.time()
        self.characters[character_id] = merged
        self._save_character(character_id, merged)
        remember_event("character.update", {"id": character_id})
        return dict(merged)

    def import_character(
        self,
        source: str | Path | Dict[str, Any],
        *,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Import character metadata from a dictionary or JSON file.

        Returns the registered record.
        """
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(path)
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            hint = str(path)
        elif isinstance(source, dict):
            payload = dict(source)
            hint = "payload"
        else:  # pragma: no cover - defensive
            raise TypeError("source must be a path or dict")

        character_id = payload.get("id") or payload.get("name")
        if not character_id:
            raise ValueError("Imported character requires an 'id' or 'name'")
        character_id = str(character_id)

        if not overwrite and character_id in self.characters:
            LOGGER.debug(
                "Character %s exists; skipping import (overwrite disabled)",
                character_id,
            )
            return dict(self.characters[character_id])

        record = self.register_character(character_id, payload)
        remember_event("character.import", {"id": character_id, "source": hint})
        return record


__all__ = ["CharacterManager"]
