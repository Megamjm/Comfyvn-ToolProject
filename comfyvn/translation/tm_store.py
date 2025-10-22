"""
Translation memory persistence used by the translation routes.

Stores source→target entries per logical key and language with metadata,
versioning, and review state so that batch translations can hit a cache and
contributors have visibility into pending strings.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from comfyvn.config.runtime_paths import config_dir


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalise_lang(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().lower().replace("_", "-")


def _normalise_key(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _entry_id(lang: str, key: str) -> str:
    payload = f"{lang}\0{key}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()


def _coerce_meta(meta: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(meta, Mapping):
        return {}
    result: Dict[str, Any] = {}
    for key, value in meta.items():
        if key is None:
            continue
        result[str(key)] = copy.deepcopy(value)
    return result


@dataclass
class TranslationMemoryEntry:
    id: str
    key: str
    lang: str
    source: str
    target: str
    origin: str
    confidence: float
    reviewed: bool
    created_at: str
    updated_at: str
    version: int = 1
    hits: int = 0
    last_requested_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_meta: bool = True) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "key": self.key,
            "lang": self.lang,
            "source": self.source,
            "target": self.target,
            "origin": self.origin,
            "confidence": self.confidence,
            "reviewed": self.reviewed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "hits": self.hits,
            "last_requested_at": self.last_requested_at,
            "reviewed_at": self.reviewed_at,
            "reviewed_by": self.reviewed_by,
        }
        if include_meta:
            payload["meta"] = copy.deepcopy(self.meta)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TranslationMemoryEntry":
        lang = _normalise_lang(payload.get("lang"))
        key = _normalise_key(payload.get("key") or payload.get("source"))
        source = _normalise_key(
            payload.get("source_text") or payload.get("source") or payload.get("src")
        )
        if not lang or not key:
            raise ValueError("translation memory entry requires lang and key")
        entry_id = str(payload.get("id") or _entry_id(lang, key))
        target = str(payload.get("target") or payload.get("target_text") or source)
        reviewed = bool(payload.get("reviewed", False))
        created_at = str(payload.get("created_at") or _now())
        updated_at = str(payload.get("updated_at") or created_at)
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        hits = int(payload.get("hits") or 0)
        version = int(payload.get("version") or 1)
        origin = str(payload.get("origin") or payload.get("source_type") or "stub")
        entry = cls(
            id=entry_id,
            key=key,
            lang=lang,
            source=source or key,
            target=target,
            origin=origin,
            confidence=confidence,
            reviewed=reviewed,
            created_at=created_at,
            updated_at=updated_at,
            version=max(version, 1),
            hits=max(hits, 0),
            last_requested_at=payload.get("last_requested_at"),
            reviewed_at=payload.get("reviewed_at"),
            reviewed_by=payload.get("reviewed_by"),
            meta=_coerce_meta(payload.get("meta")),
        )
        return entry


class TranslationMemoryStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._path = Path(store_path) if store_path else config_dir("i18n", "tm.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)

        self._entries: Dict[str, TranslationMemoryEntry] = {}
        self._lang_index: Dict[str, Dict[str, str]] = {}
        self._lang_source_index: Dict[str, Dict[str, str]] = {}

        self._load()

    # ------------------------------------------------------------------ #
    # Lookup / mutation helpers
    # ------------------------------------------------------------------ #
    def lookup(
        self, key: str, lang: str, *, include_meta: bool = True
    ) -> Optional[Dict[str, Any]]:
        item_key = _normalise_key(key)
        language = _normalise_lang(lang)
        if not item_key or not language:
            return None

        with self._lock:
            entry = self._get_entry_locked(language, item_key)
            if entry is None:
                return None
            entry.hits += 1
            entry.last_requested_at = _now()
            self._persist_locked()
            return entry.to_dict(include_meta=include_meta)

    def record(
        self,
        *,
        key: str | None,
        lang: str,
        source_text: str | None = None,
        target_text: str | None = None,
        origin: str = "stub",
        confidence: float = 0.0,
        reviewed: bool = False,
        meta: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        item_key = _normalise_key(key)
        base_text = _normalise_key(source_text)
        if not item_key and base_text:
            item_key = base_text
        language = _normalise_lang(lang)
        if not item_key or not language:
            raise ValueError("key/source_text and lang must be provided")
        meta_payload = _coerce_meta(meta)
        source_value = base_text or item_key
        target_value = str(target_text) if target_text is not None else source_value
        origin_value = origin or "stub"
        now = _now()

        with self._lock:
            entry = self._get_entry_locked(language, item_key)
            if entry:
                changed = False
                if entry.key != item_key:
                    self._remove_index_locked(entry)
                    entry.key = item_key
                    changed = True
                if target_text is not None and target_value != entry.target:
                    entry.target = target_value
                    changed = True
                if source_value and source_value != entry.source:
                    entry.source = source_value
                    changed = True
                if meta_payload:
                    before_meta = copy.deepcopy(entry.meta)
                    entry.meta.update(meta_payload)
                    if entry.meta != before_meta:
                        changed = True
                if origin_value and origin_value != entry.origin:
                    entry.origin = origin_value
                    changed = True
                if confidence > entry.confidence:
                    entry.confidence = confidence
                if reviewed and not entry.reviewed:
                    entry.reviewed = True
                    entry.reviewed_at = now
                    changed = True
                entry.updated_at = now
                if changed:
                    entry.version += 1
                self._index_entry_locked(entry)
                self._persist_locked()
                return entry.to_dict(include_meta=True)

            entry = TranslationMemoryEntry(
                id=_entry_id(language, item_key),
                key=item_key,
                lang=language,
                source=source_value,
                target=target_value,
                origin=origin_value,
                confidence=float(confidence or 0.0),
                reviewed=bool(reviewed),
                created_at=now,
                updated_at=now,
                version=1,
                meta=meta_payload,
            )
            if entry.reviewed:
                entry.reviewed_at = now
            self._entries[entry.id] = entry
            self._index_entry_locked(entry)
            self._persist_locked()
            return entry.to_dict(include_meta=True)

    def approve(
        self,
        entry_id: str,
        *,
        translation: Optional[str] = None,
        reviewer: Optional[str] = None,
        confidence: float | None = None,
        meta: Optional[Mapping[str, Any]] = None,
        reviewed: Optional[bool] = None,
        origin: Optional[str] = None,
        source_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        identifier = _normalise_key(entry_id)
        if not identifier:
            raise KeyError("entry id required")

        with self._lock:
            entry = self._entries.get(identifier)
            if entry is None:
                raise KeyError(identifier)
            now = _now()
            changed = False
            target_value = translation if translation is not None else entry.target
            if translation is not None and target_value != entry.target:
                entry.target = target_value
                changed = True
            if source_text is not None:
                source_value = _normalise_key(source_text) or entry.source
                if source_value != entry.source:
                    entry.source = source_value
                    changed = True
            if meta is not None:
                new_meta = _coerce_meta(meta)
                if new_meta:
                    before_meta = copy.deepcopy(entry.meta)
                    entry.meta.update(new_meta)
                    if entry.meta != before_meta:
                        changed = True
            if origin and origin != entry.origin:
                entry.origin = origin
                changed = True
            entry.updated_at = now
            if changed:
                entry.version += 1
            if confidence is not None:
                entry.confidence = float(confidence)
            else:
                entry.confidence = max(entry.confidence, 0.95)
            if reviewer:
                entry.reviewed_by = reviewer
            if reviewed is None or reviewed:
                entry.reviewed = True
                entry.reviewed_at = now
            else:
                entry.reviewed = False
                entry.reviewed_at = None
            self._index_entry_locked(entry)
            self._persist_locked()
            return entry.to_dict(include_meta=True)

    def pending(
        self,
        lang: str | None = None,
        *,
        key: str | None = None,
        limit: Optional[int] = None,
        meta_contains: Optional[Mapping[str, Any]] = None,
        include_meta: bool = True,
    ) -> List[Dict[str, Any]]:
        return self._collect_entries(
            reviewed=False,
            lang=lang,
            key=key,
            limit=limit,
            meta_contains=meta_contains,
            include_meta=include_meta,
        )

    def reviewed(
        self,
        lang: str | None = None,
        *,
        key: str | None = None,
        limit: Optional[int] = None,
        meta_contains: Optional[Mapping[str, Any]] = None,
        include_meta: bool = True,
    ) -> List[Dict[str, Any]]:
        return self._collect_entries(
            reviewed=True,
            lang=lang,
            key=key,
            limit=limit,
            meta_contains=meta_contains,
            include_meta=include_meta,
        )

    def export_json(
        self,
        lang: str | None = None,
        *,
        key: str | None = None,
        include_meta: bool = False,
    ) -> Dict[str, Any]:
        reviewed_entries = self.reviewed(
            lang=lang,
            key=key,
            include_meta=include_meta,
        )
        payload = {
            "generated_at": _now(),
            "entries": [
                {
                    "id": item["id"],
                    "key": item["key"],
                    "lang": item["lang"],
                    "source": item["source"],
                    "target": item["target"],
                    "version": item.get("version", 1),
                    "confidence": item.get("confidence", 1.0),
                    "reviewed_at": item.get("reviewed_at"),
                    "reviewed_by": item.get("reviewed_by"),
                    "origin": item.get("origin", "tm"),
                    **(
                        {"meta": copy.deepcopy(item.get("meta", {}))}
                        if include_meta
                        else {}
                    ),
                }
                for item in reviewed_entries
            ],
        }
        if lang:
            payload["lang"] = _normalise_lang(lang)
        if key:
            payload["key"] = key
        return payload

    def export_po(
        self,
        lang: str | None = None,
        *,
        key: str | None = None,
        include_meta: bool = False,
    ) -> str:
        reviewed_entries = self.reviewed(
            lang=lang,
            key=key,
            include_meta=include_meta,
        )
        lines: List[str] = []
        if lang:
            lines.append(f"# Export lang: {_normalise_lang(lang)}")
        else:
            lines.append("# Export lang: mixed")
        if key:
            lines.append(f"# Scoped key: {key}")
        lines.append(f"# Generated at: {_now()}")
        lines.append("")
        for item in reviewed_entries:
            lines.append(f"# Key: {item['key']}")
            lines.append(f"# Version: {item.get('version', 1)}")
            if include_meta and item.get("meta"):
                for meta_key, meta_value in item["meta"].items():
                    lines.append(f"# Meta {meta_key}: {json.dumps(meta_value)}")
            lines.extend(
                [
                    f'msgctxt "{item["lang"]}"',
                    f'msgid {self._quote_po(item["source"])}',
                    f'msgstr {self._quote_po(item["target"])}',
                    "",
                ]
            )
        return "\n".join(lines).strip() + "\n"

    def stats(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            pending_counts: Dict[str, int] = {}
            reviewed_counts: Dict[str, int] = {}
            for entry in self._entries.values():
                bucket = reviewed_counts if entry.reviewed else pending_counts
                bucket[entry.lang] = bucket.get(entry.lang, 0) + 1
        return {"pending": pending_counts, "reviewed": reviewed_counts}

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #
    def _collect_entries(
        self,
        *,
        reviewed: bool,
        lang: str | None,
        key: str | None,
        limit: Optional[int],
        meta_contains: Optional[Mapping[str, Any]],
        include_meta: bool,
    ) -> List[Dict[str, Any]]:
        language = _normalise_lang(lang) if lang else None
        meta_filter = _coerce_meta(meta_contains)
        with self._lock:
            items = [
                entry.to_dict(include_meta=include_meta)
                for entry in self._entries.values()
                if entry.reviewed == reviewed
                and (language is None or entry.lang == language)
                and (key is None or entry.key == key)
                and self._matches_meta(entry, meta_filter)
            ]
        items.sort(key=lambda item: (item.get("created_at") or "", item["id"]))
        limit_value = self._coerce_limit(limit)
        if limit_value is not None:
            items = items[:limit_value]
        return items

    def _get_entry_locked(
        self, lang: str, key: str
    ) -> Optional[TranslationMemoryEntry]:
        lang_map = self._lang_index.get(lang)
        if lang_map and key in lang_map:
            entry = self._entries.get(lang_map[key])
            if entry:
                return entry
        source_map = self._lang_source_index.get(lang)
        if source_map and key in source_map:
            entry = self._entries.get(source_map[key])
            if entry:
                return entry
        entry = self._entries.get(key)
        if entry and entry.lang == lang:
            return entry
        return None

    def _index_entry_locked(self, entry: TranslationMemoryEntry) -> None:
        self._remove_index_locked(entry)
        lang_map = self._lang_index.setdefault(entry.lang, {})
        lang_map[entry.key] = entry.id
        source_map = self._lang_source_index.setdefault(entry.lang, {})
        source_map[entry.source] = entry.id

    def _remove_index_locked(self, entry: TranslationMemoryEntry) -> None:
        lang_map = self._lang_index.get(entry.lang)
        if lang_map:
            stale = [key for key, value in lang_map.items() if value == entry.id]
            for key in stale:
                lang_map.pop(key, None)
            if not lang_map:
                self._lang_index.pop(entry.lang, None)
        source_map = self._lang_source_index.get(entry.lang)
        if source_map:
            stale = [key for key, value in source_map.items() if value == entry.id]
            for key in stale:
                source_map.pop(key, None)
            if not source_map:
                self._lang_source_index.pop(entry.lang, None)

    def _matches_meta(
        self, entry: TranslationMemoryEntry, meta_filter: Dict[str, Any]
    ) -> bool:
        if not meta_filter:
            return True
        for key, value in meta_filter.items():
            if entry.meta.get(key) != value:
                return False
        return True

    def _coerce_limit(self, limit: Optional[int]) -> Optional[int]:
        if limit is None:
            return None
        try:
            parsed = int(limit)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

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
            self._index_entry_locked(entry)

    def _persist_locked(self) -> None:
        data = {
            "entries": [
                entry.to_dict(include_meta=True) for entry in self._entries.values()
            ],
            "updated_at": _now(),
        }
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        try:
            self._path.write_text(payload, encoding="utf-8")
        except Exception:
            # Persistence failures should not crash callers.
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
