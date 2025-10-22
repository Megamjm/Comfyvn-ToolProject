"""
Lightweight translation manager for ComfyVN.

This module centralises language lookup and persistence of the active
language flag inside ``config/comfyvn.json`` while loading translation
tables from either embedded config entries or JSON files placed under
``config/i18n`` (user overrides) and ``data/i18n`` (shipped defaults).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional

from comfyvn.config.runtime_paths import config_dir, data_dir
from comfyvn.translation.tm_store import get_store

LOGGER = logging.getLogger(__name__)


class TranslationManager:
    """Manage translation tables and the active language flag."""

    def __init__(
        self,
        *,
        fallback_language: str = "en",
        config_path: Path | None = None,
        translation_dirs: Optional[Iterable[Path | str]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._fallback_language = self._normalise_lang(fallback_language) or "en"
        self._tables: Dict[str, Dict[str, str]] = {}
        self._loaded_langs: set[str] = set()

        self._config_path = (
            Path(config_path) if config_path else config_dir("comfyvn.json")
        )
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        self._config_candidates: tuple[Path, ...] = tuple(
            dict.fromkeys(
                [
                    self._config_path,
                    Path("config/comfyvn.json"),
                    Path("comfyvn.json"),
                ]
            )
        )

        dirs: list[Path] = []
        if translation_dirs:
            for entry in translation_dirs:
                dirs.append(Path(entry))
        else:
            dirs.extend([config_dir("i18n"), data_dir("i18n")])
        # Preserve order but drop duplicates while ensuring directories exist.
        self._translation_dirs: tuple[Path, ...] = tuple(
            dict.fromkeys(dir_path for dir_path in dirs if dir_path)
        )
        for directory in self._translation_dirs:
            directory.mkdir(parents=True, exist_ok=True)

        self._active_language = self._fallback_language
        self._load_state()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get_active_language(self) -> str:
        with self._lock:
            return self._active_language

    def set_active_language(self, language: str) -> str:
        normalised = self._normalise_lang(language)
        if not normalised:
            raise ValueError("language must be a non-empty string")
        with self._lock:
            if normalised == self._active_language:
                return self._active_language
            self._active_language = normalised
            self._ensure_table_locked(normalised)
            self._persist_locked()
            return self._active_language

    def set_fallback_language(self, language: str) -> str:
        normalised = self._normalise_lang(language)
        if not normalised:
            raise ValueError("fallback language must be a non-empty string")
        with self._lock:
            if normalised == self._fallback_language:
                return self._fallback_language
            self._fallback_language = normalised
            self._ensure_table_locked(normalised)
            self._persist_locked()
            return self._fallback_language

    def get_fallback_language(self) -> str:
        with self._lock:
            return self._fallback_language

    def available_languages(self) -> list[str]:
        with self._lock:
            discovered = set(self._tables.keys())
            discovered.add(self._fallback_language)
            discovered.add(self._active_language)
            for directory in self._translation_dirs:
                for path in directory.glob("*.json"):
                    discovered.add(self._normalise_lang(path.stem) or path.stem)
            return sorted(discovered)

    def get_table_value(self, key: str, lang: str) -> Optional[str]:
        normalised_lang = self._normalise_lang(lang)
        if not key or not normalised_lang:
            return None
        with self._lock:
            return self._lookup_locked(normalised_lang, key)

    def t(self, key: str, lang: str | None = None, *, fallback: bool = True) -> str:
        if not key:
            return ""
        requested = self._normalise_lang(lang) if lang else None
        with self._lock:
            primary = requested or self._active_language
            value = self._lookup_locked(primary, key)
            if value is not None:
                return value
        store_value = self._lookup_tm(primary, key)
        if store_value is not None:
            return store_value
        if fallback:
            fallback_lang = self._fallback_language
            if primary != fallback_lang:
                with self._lock:
                    value = self._lookup_locked(fallback_lang, key)
                    if value is not None:
                        return value
                store_value = self._lookup_tm(fallback_lang, key)
                if store_value is not None:
                    return store_value
        return key

    def batch_identity(self, strings: Iterable[str]) -> list[dict[str, str]]:
        """Return a stub translation batch (identity mapping)."""
        return [{"src": s, "tgt": s} for s in strings]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _normalise_lang(self, value: str | None) -> str:
        if not value:
            return ""
        return str(value).strip().lower().replace("_", "-")

    def _lookup_locked(self, lang: str, key: str) -> Optional[str]:
        self._ensure_table_locked(lang)
        table = self._tables.get(lang) or {}
        if key in table:
            return table[key]
        # Provide dot-path fallback: try parent keys (e.g. ui.menu.item -> ui.menu)
        parts = key.split(".")
        while len(parts) > 1:
            parts.pop()
            candidate = ".".join(parts)
            if candidate in table:
                return table[candidate]
        return None

    def _ensure_table_locked(self, lang: str) -> None:
        if not lang or lang in self._loaded_langs:
            return
        existing = self._tables.get(lang)
        mapping: Dict[str, str] = dict(existing or {})
        for path in self._iter_translation_files(lang):
            loaded = self._load_table_from_file(path)
            if loaded:
                mapping.update(loaded)
        self._tables[lang] = mapping
        self._loaded_langs.add(lang)

    def _iter_translation_files(self, lang: str) -> Iterable[Path]:
        candidates = []
        filename = f"{lang}.json"
        for directory in self._translation_dirs:
            candidate = directory / filename
            if candidate.exists():
                candidates.append(candidate)
        return candidates

    def _load_state(self) -> None:
        cfg = self._read_config()
        i18n = cfg.get("i18n")
        if isinstance(i18n, Mapping):
            active = self._normalise_lang(self._coerce_str(i18n.get("active_language")))
            fallback = self._normalise_lang(
                self._coerce_str(i18n.get("fallback_language"))
            )
            if fallback:
                self._fallback_language = fallback
            if active:
                self._active_language = active
            tables = i18n.get("tables")
            if isinstance(tables, Mapping):
                for lang, table in tables.items():
                    normalised = self._normalise_lang(str(lang))
                    if not normalised:
                        continue
                    mapping = self._coerce_table(table)
                    if mapping:
                        self._tables.setdefault(normalised, {}).update(mapping)
        # Ensure fallback + active always have an entry even if empty.
        self._tables.setdefault(self._fallback_language, {})
        self._tables.setdefault(self._active_language, {})
        self._ensure_table_locked(self._fallback_language)
        if self._active_language != self._fallback_language:
            # Make sure on-disk overrides are visible immediately.
            self._ensure_table_locked(self._active_language)

    def _persist_locked(self) -> None:
        cfg = self._read_config()
        if not isinstance(cfg, MutableMapping):
            cfg = {}
        i18n = cfg.get("i18n")
        if not isinstance(i18n, MutableMapping):
            i18n = {}
        i18n["active_language"] = self._active_language
        i18n["fallback_language"] = self._fallback_language
        # Persist only explicit inline tables; user file overrides stay on disk.
        inline_tables = {
            lang: table
            for lang, table in self._tables.items()
            if table
            and not any(
                (directory / f"{lang}.json").exists()
                for directory in self._translation_dirs
            )
        }
        if inline_tables:
            i18n["tables"] = inline_tables
        elif "tables" in i18n:
            i18n.pop("tables")
        cfg["i18n"] = i18n
        payload = json.dumps(cfg, indent=2, ensure_ascii=False)
        try:
            self._config_path.write_text(payload, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning(
                "Failed to persist i18n config to %s: %s", self._config_path, exc
            )

    def _read_config(self) -> Dict[str, Any]:
        for path in self._config_candidates:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.debug("Skipping unreadable config %s (%s)", path, exc)
                continue
            if isinstance(data, dict):
                return data
        return {}

    @staticmethod
    def _coerce_str(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _coerce_table(value: Any) -> Dict[str, str]:
        if isinstance(value, Mapping):
            # Prefer nested "strings"/"items" structures if present.
            if "strings" in value and isinstance(value["strings"], Mapping):
                source = value["strings"]
            elif "items" in value and isinstance(value["items"], Iterable):
                source = {}
                for item in value["items"]:
                    if isinstance(item, Mapping):
                        key = item.get("key")
                        text = item.get("text") or item.get("value")
                        if key is not None and text is not None:
                            source[str(key)] = str(text)
                return source
            else:
                source = value
            return {
                str(k): str(v)
                for k, v in source.items()
                if k is not None and v is not None
            }
        if isinstance(value, Iterable):
            result: Dict[str, str] = {}
            for item in value:
                if not isinstance(item, Mapping):
                    continue
                key = item.get("key")
                text = item.get("text") or item.get("value")
                if key is not None and text is not None:
                    result[str(key)] = str(text)
            return result
        return {}

    def _load_table_from_file(self, path: Path) -> Dict[str, str]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Skipping unreadable translation file %s (%s)", path, exc)
            return {}
        mapping = self._coerce_table(data)
        if not mapping and isinstance(data, Mapping):
            lang = self._normalise_lang(str(data.get("lang") or path.stem))
            payload = data.get("strings") or data.get("items") or data.get("values")
            mapping = self._coerce_table(payload)
            if not mapping and isinstance(data, Mapping):
                # Flatten nested dicts where values are plain strings.
                mapping = {
                    str(k): str(v)
                    for k, v in data.items()
                    if isinstance(k, str) and isinstance(v, str)
                }
        return mapping

    def _lookup_tm(self, lang: str, key: str) -> Optional[str]:
        normalised_lang = self._normalise_lang(lang)
        if not key or not normalised_lang:
            return None
        try:
            store = get_store()
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Translation memory unavailable: %s", exc)
            return None
        try:
            payload = store.lookup(key, normalised_lang, include_meta=False)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug(
                "Translation memory lookup failed for %s/%s: %s",
                key,
                normalised_lang,
                exc,
            )
            return None
        if payload and isinstance(payload, Mapping):
            candidate = payload.get("target")
            if isinstance(candidate, str) and candidate:
                return candidate
        return None


_MANAGER: Optional[TranslationManager] = None


def get_manager() -> TranslationManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = TranslationManager()
    return _MANAGER


def t(key: str, lang: str | None = None, *, fallback: bool = True) -> str:
    return get_manager().t(key, lang, fallback=fallback)
