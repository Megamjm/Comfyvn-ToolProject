"""
Translation memory persistence used by the translation routes.

Stores source→target entries per language with lightweight metadata so that
stubbed batch translations can hit a cache and the review queue can approve /
edit items before exporting reviewed strings.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from comfyvn.config.runtime_paths import config_dir


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalise_lang(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().lower().replace("_", "-")


def _entry_id(lang: str, source: str) -> str:
    payload = f"{lang}\0{source}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()


@dataclass
class TranslationMemoryEntry:
    id: str
    lang: str
    source: str
    target: str
    confidence: float
    reviewed: bool
    created_at: str
    updated_at: str
    hits: int = 0
    last_requested_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "lang": self.lang,
            "source": self.source,
            "target": self.target,
            "confidence": self.confidence,
            "reviewed": self.reviewed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "hits": self.hits,
            "last_requested_at": self.last_requested_at,
            "reviewed_at": self.reviewed_at,
            "reviewed_by": self.reviewed_by,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TranslationMemoryEntry":
        lang = _normalise_lang(payload.get("lang"))
        source = str(payload.get("source") or "")
        if not lang or not source:
            raise ValueError("translation memory entry requires lang and source")
        entry_id = str(payload.get("id") or _entry_id(lang, source))
        target = str(payload.get("target") or source)
        reviewed = bool(payload.get("reviewed", False))
        created_at = str(payload.get("created_at") or _now())
        updated_at = str(payload.get("updated_at") or created_at)
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        hits = int(payload.get("hits") or 0)
        entry = cls(
            id=entry_id,
            lang=lang,
            source=source,
            target=target,
            confidence=confidence,
            reviewed=reviewed,
            created_at=created_at,
            updated_at=updated_at,
            hits=max(hits, 0),
            last_requested_at=payload.get("last_requested_at"),
            reviewed_at=payload.get("reviewed_at"),
            reviewed_by=payload.get("reviewed_by"),
        )
        return entry


class TranslationMemoryStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._path = Path(store_path) if store_path else config_dir("i18n", "tm.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)

        self._entries: Dict[str, TranslationMemoryEntry] = {}
        self._lang_index: Dict[str, Dict[str, str]] = {}

        self._load()

    # ------------------------------------------------------------------ #
    # Lookup / mutation helpers
    # ------------------------------------------------------------------ #
    def lookup(self, source: str, lang: str) -> Optional[Dict[str, Any]]:
        key = str(source or "")
        language = _normalise_lang(lang)
        if not key or not language:
            return None

        with self._lock:
            entry_id = self._lang_index.get(language, {}).get(key)
            if not entry_id:
                return None
            entry = self._entries.get(entry_id)
            if not entry:
                return None
            entry.hits += 1
            entry.last_requested_at = _now()
            self._persist_locked()
            return copy.deepcopy(entry.to_dict())

    def record(
        self,
        *,
        source: str,
        target: str,
        lang: str,
        confidence: float = 0.0,
        reviewed: bool = False,
    ) -> Dict[str, Any]:
        key = str(source or "")
        language = _normalise_lang(lang)
        if not key or not language:
            raise ValueError("source and lang must be provided")
        now = _now()

        with self._lock:
            entry_id = self._lang_index.get(language, {}).get(key)
            if entry_id and entry_id in self._entries:
                entry = self._entries[entry_id]
                entry.target = target
                entry.updated_at = now
                entry.reviewed = bool(reviewed) or entry.reviewed
                if confidence > entry.confidence:
                    entry.confidence = confidence
                if entry.reviewed and entry.reviewed_at is None:
                    entry.reviewed_at = now
                self._persist_locked()
                return copy.deepcopy(entry.to_dict())

            entry = TranslationMemoryEntry(
                id=_entry_id(language, key),
                lang=language,
                source=key,
                target=target,
                confidence=confidence,
                reviewed=bool(reviewed),
                created_at=now,
                updated_at=now,
            )
            self._entries[entry.id] = entry
            lang_map = self._lang_index.setdefault(language, {})
            lang_map[key] = entry.id
            self._persist_locked()
            return copy.deepcopy(entry.to_dict())

    def approve(
        self,
        entry_id: str,
        *,
        translation: Optional[str] = None,
        reviewer: Optional[str] = None,
        confidence: float | None = None,
    ) -> Dict[str, Any]:
        identifier = str(entry_id or "")
        if not identifier:
            raise KeyError("entry id required")

        with self._lock:
            entry = self._entries.get(identifier)
            if entry is None:
                raise KeyError(identifier)
            if translation is not None:
                entry.target = translation
            entry.reviewed = True
            now = _now()
            entry.updated_at = now
            entry.reviewed_at = now
            if reviewer:
                entry.reviewed_by = reviewer
            entry.confidence = (
                float(confidence)
                if confidence is not None
                else max(entry.confidence, 0.95)
            )
            self._persist_locked()
            return copy.deepcopy(entry.to_dict())

    def pending(self, lang: str | None = None) -> List[Dict[str, Any]]:
        language = _normalise_lang(lang) if lang else None
        with self._lock:
            items = [
                copy.deepcopy(entry.to_dict())
                for entry in self._entries.values()
                if not entry.reviewed and (language is None or entry.lang == language)
            ]
        items.sort(key=lambda item: (item.get("created_at") or "", item["id"]))
        return items

    def reviewed(self, lang: str | None = None) -> List[Dict[str, Any]]:
        language = _normalise_lang(lang) if lang else None
        with self._lock:
            items = [
                copy.deepcopy(entry.to_dict())
                for entry in self._entries.values()
                if entry.reviewed and (language is None or entry.lang == language)
            ]
        items.sort(key=lambda item: (item.get("updated_at") or "", item["id"]))
        return items

    def export_json(self, lang: str | None = None) -> Dict[str, Any]:
        reviewed_entries = self.reviewed(lang=lang)
        payload = {
            "generated_at": _now(),
            "entries": [
                {
                    "id": item["id"],
                    "lang": item["lang"],
                    "source": item["source"],
                    "target": item["target"],
                    "confidence": item.get("confidence", 1.0),
                    "reviewed_at": item.get("reviewed_at"),
                    "reviewed_by": item.get("reviewed_by"),
                }
                for item in reviewed_entries
            ],
        }
        if lang:
            payload["lang"] = _normalise_lang(lang)
        return payload

    def export_po(self, lang: str | None = None) -> str:
        reviewed_entries = self.reviewed(lang=lang)
        lines: List[str] = []
        if lang:
            lines.append(f"# Export lang: {_normalise_lang(lang)}")
        else:
            lines.append("# Export lang: mixed")
        lines.append(f"# Generated at: {_now()}")
        lines.append("")
        for item in reviewed_entries:
            lines.extend(
                [
                    f'msgctxt "{item["lang"]}"',
                    f'msgid {self._quote_po(item["source"])}',
                    f'msgstr {self._quote_po(item["target"])}',
                    "",
                ]
            )
        return "\n".join(lines).strip() + "\n"

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        entries = data.get("entries")
        if not isinstance(entries, Iterable):
            return
        for payload in entries:
            if not isinstance(payload, dict):
                continue
            try:
                entry = TranslationMemoryEntry.from_dict(payload)
            except Exception:
                continue
            self._entries[entry.id] = entry
            lang_map = self._lang_index.setdefault(entry.lang, {})
            lang_map[entry.source] = entry.id

    def _persist_locked(self) -> None:
        data = {
            "entries": [entry.to_dict() for entry in self._entries.values()],
            "updated_at": _now(),
        }
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        try:
            self._path.write_text(payload, encoding="utf-8")
        except Exception:
            # Persistence failure should not crash callers; log softer later if needed.
            pass

    @staticmethod
    def _quote_po(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'


_STORE: TranslationMemoryStore | None = None
_STORE_LOCK = threading.RLock()


def get_store() -> TranslationMemoryStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = TranslationMemoryStore()
        return _STORE


def set_store(store: TranslationMemoryStore | None) -> None:
    global _STORE
    with _STORE_LOCK:
        _STORE = store
