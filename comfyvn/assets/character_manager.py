from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from comfyvn.config.runtime_paths import data_dir
from comfyvn.core.memory_engine import remember_event

LOGGER = logging.getLogger(__name__)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: Any, fallback: str = "character") -> str:
    text = str(value or "").strip().lower()
    if not text:
        return fallback
    slug = _SLUG_RE.sub("-", text).strip("-")
    return slug or fallback


class CharacterManager:
    """Lightweight registry for player and NPC character metadata."""

    CHARACTER_FILENAME = "character.json"
    LORA_FILENAME = "lora.json"

    def __init__(self, data_path: str | Path | None = None) -> None:
        self.data_path = Path(data_path) if data_path else data_dir("characters")
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.characters: Dict[str, Dict[str, Any]] = {}
        self._load_existing()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------
    def character_dir(self, character_id: str) -> Path:
        return self.data_path / character_id

    def _character_path(self, character_id: str) -> Path:
        return self.character_dir(character_id) / self.CHARACTER_FILENAME

    def _legacy_path(self, character_id: str) -> Path:
        return self.data_path / f"{character_id}.json"

    def _loras_path(self, character_id: str) -> Path:
        return self.character_dir(character_id) / self.LORA_FILENAME

    def _legacy_loras_path(self, character_id: str) -> Path:
        return self.data_path / f"{character_id}.lora.json"

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------
    def _load_existing(self) -> None:
        self.characters.clear()
        handled: set[str] = set()

        # Prefer new folder-based layout
        for entry in sorted(self.data_path.iterdir()):
            if not entry.is_dir():
                continue
            char_file = entry / self.CHARACTER_FILENAME
            if not char_file.exists():
                continue
            payload = self._read_json(char_file)
            if payload is None:
                continue
            character_id = str(payload.get("id") or entry.name).strip() or entry.name
            record = self._normalise_record(character_id, payload)
            self.characters[character_id] = record
            handled.add(character_id)

        # Legacy flat files (data/characters/<id>.json)
        for file in sorted(self.data_path.glob("*.json")):
            character_id = file.stem
            if character_id in handled:
                continue
            payload = self._read_json(file)
            if payload is None:
                continue
            resolved_id = str(payload.get("id") or character_id).strip() or character_id
            if resolved_id in handled:
                continue
            record = self._normalise_record(resolved_id, payload)
            self.characters[resolved_id] = record
            handled.add(resolved_id)

        if not self.characters:
            self._load_defaults()

    def _load_defaults(self) -> None:
        defaults_dir = Path(__file__).resolve().parents[2] / "defaults" / "characters"
        if not defaults_dir.exists():
            return
        for entry in sorted(defaults_dir.glob("*.json")):
            payload = self._read_json(entry)
            if payload is None:
                continue
            character_id = str(payload.get("id") or entry.stem).strip() or entry.stem
            if character_id in self.characters:
                continue
            record = self._normalise_record(character_id, payload)
            self.characters[character_id] = record
            try:
                self._save_character(character_id, record)
            except Exception as exc:
                LOGGER.debug(
                    "Failed to persist default character %s: %s", character_id, exc
                )

    def _read_json(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Skipping character %s (invalid json): %s", path, exc)
            return None
        if not isinstance(data, dict):
            LOGGER.warning("Character payload at %s must be a JSON object", path)
            return None
        return data

    def _normalise_record(
        self, character_id: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = dict(record or {})
        payload["id"] = character_id
        payload.setdefault("name", payload.get("display_name") or character_id)
        payload.setdefault("display_name", payload["name"])
        payload["tags"] = self._normalise_tags(payload.get("tags"))
        payload["avatars"] = self._normalise_avatars(payload.get("avatars"))
        if "loras" in payload and payload["loras"] is not None:
            payload["loras"] = self._normalise_loras(payload.get("loras"))
        else:
            payload["loras"] = self._load_loras(character_id)
        payload.setdefault("created_at", payload.get("created_at") or time.time())
        payload.setdefault(
            "updated_at", payload.get("updated_at") or payload["created_at"]
        )
        pose = payload.get("pose") or payload.get("default_pose")
        if pose is not None:
            payload["pose"] = str(pose)
        expression = payload.get("expression") or payload.get("default_expression")
        if expression is not None:
            payload["expression"] = str(expression)
        if "meta" in payload and not isinstance(payload["meta"], dict):
            # Preserve raw meta text under notes to avoid data loss.
            payload.setdefault("notes", payload["meta"])
            payload["meta"] = {}
        payload.setdefault("meta", {})
        return payload

    def _save_character(self, character_id: str, payload: Dict[str, Any]) -> None:
        serialisable = dict(payload)
        path = self._character_path(character_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(serialisable, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Maintain legacy flat file for compatibility
        legacy = self._legacy_path(character_id)
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(
            json.dumps(serialisable, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _save_loras(
        self, character_id: str, entries: Sequence[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        loras = self._normalise_loras(entries)
        path = self._loras_path(character_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        legacy = self._legacy_loras_path(character_id)
        if loras:
            payload = {"loras": loras}
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            legacy.write_text(
                json.dumps(loras, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        else:
            path.unlink(missing_ok=True)
            legacy.unlink(missing_ok=True)
        return loras

    def _load_loras(self, character_id: str) -> List[Dict[str, Any]]:
        candidates = [
            self._loras_path(character_id),
            self._legacy_loras_path(character_id),
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                LOGGER.warning("Skipping LoRA config for %s (%s)", character_id, exc)
                continue
            return self._normalise_loras(data)
        return []

    @staticmethod
    def _normalise_tags(value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, str):
            parts = re.split(r"[,\n]", value)
            return [chunk.strip() for chunk in parts if chunk.strip()]
        if isinstance(value, (list, set, tuple)):
            tags: List[str] = []
            for item in value:
                if item is None:
                    continue
                chunk = str(item).strip()
                if chunk:
                    tags.append(chunk)
            return tags
        return []

    @staticmethod
    def _normalise_avatars(value: Any) -> List[Dict[str, Any]]:
        if not value:
            return []
        avatars: List[Dict[str, Any]] = []
        if isinstance(value, list):
            items: Iterable[Any] = value
        else:
            items = [value]
        for entry in items:
            if isinstance(entry, dict):
                avatars.append(dict(entry))
            elif entry:
                avatars.append({"path": str(entry)})
        return avatars

    @staticmethod
    def _normalise_loras(value: Any) -> List[Dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, dict):
            items = value.get("loras")
        else:
            items = value
        if not isinstance(items, list):
            return []
        entries: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("name") or "").strip()
            if not path:
                continue
            entry: Dict[str, Any] = {"path": path}
            weight = item.get("weight", item.get("strength"))
            if weight is not None:
                try:
                    entry["weight"] = float(weight)
                except (TypeError, ValueError):
                    pass
            if item.get("clip") is not None:
                try:
                    entry["clip"] = float(item["clip"])
                except (TypeError, ValueError):
                    pass
            source = item.get("source")
            if source:
                entry["source"] = str(source)
            entries.append(entry)
        seen: set[str] = set()
        deduped: List[Dict[str, Any]] = []
        for entry in entries:
            key = entry["path"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entry)
        return deduped

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

    def resolve_character(self, reference: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Resolve a character by id or display name (case-insensitive).

        Returns a tuple of (character_id, record) or None.
        """
        if not reference:
            return None
        ref = str(reference).strip()
        direct = self.get_character(ref)
        if direct:
            return ref, direct
        ref_lower = ref.casefold()
        for character_id, record in self.characters.items():
            name = str(record.get("name") or "").strip()
            if name and name.casefold() == ref_lower:
                return character_id, dict(record)
        return None

    def register_character(
        self, character_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create or update a character record."""
        character_id = str(character_id).strip()
        if not character_id:
            raise ValueError("character_id is required")
        base = dict(self.characters.get(character_id, {}) or {})
        created_at = base.get("created_at") or time.time()
        merged = dict(base)
        merged.update(payload or {})
        merged.setdefault("created_at", created_at)
        record = self._normalise_record(character_id, merged)
        record["created_at"] = created_at
        record["updated_at"] = time.time()
        self.characters[character_id] = record
        self._save_character(character_id, record)
        self._save_loras(character_id, record.get("loras") or [])
        remember_event(
            "character.register",
            {"id": character_id, "name": record.get("name")},
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
        merged["created_at"] = existing.get("created_at") or merged.get("created_at")
        merged = self._normalise_record(character_id, merged)
        merged["updated_at"] = time.time()
        self.characters[character_id] = merged
        self._save_character(character_id, merged)
        self._save_loras(character_id, merged.get("loras") or [])
        remember_event("character.update", {"id": character_id})
        return dict(merged)

    def set_loras(
        self, character_id: str, entries: Sequence[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Persist LoRA attachments for a character and update in-memory cache."""
        record = self.characters.get(character_id)
        if not record:
            raise KeyError(f"character '{character_id}' not found")
        loras = self._save_loras(character_id, entries)
        record["loras"] = loras
        self._save_character(character_id, record)
        return list(loras)

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
        character_id = _slugify(character_id)

        if not overwrite and character_id in self.characters:
            LOGGER.debug(
                "Character %s exists; skipping import (overwrite disabled)",
                character_id,
            )
            return dict(self.characters[character_id])

        record = self.register_character(character_id, payload)
        remember_event("character.import", {"id": character_id, "source": hint})
        return record


__all__ = ["CharacterManager", "_slugify"]
