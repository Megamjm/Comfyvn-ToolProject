"""
Asset registry facade for the Studio shell.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
import wave
from array import array
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from comfyvn.config.runtime_paths import thumb_cache_dir
from comfyvn.core import modder_hooks

try:  # thumbnail generation optional
    from PIL import (
        Image,  # type: ignore
        PngImagePlugin,  # type: ignore
    )
except Exception:  # pragma: no cover - pillow optional
    Image = None  # type: ignore
    PngImagePlugin = None  # type: ignore

try:  # audio tagging optional
    from mutagen.flac import FLAC  # type: ignore
    from mutagen.id3 import ID3, TXXX, ID3NoHeaderError  # type: ignore
    from mutagen.mp3 import MP3  # type: ignore
    from mutagen.oggvorbis import OggVorbis  # type: ignore
    from mutagen.wave import WAVE  # type: ignore
except Exception:  # pragma: no cover - mutagen optional
    ID3 = None  # type: ignore
    TXXX = None  # type: ignore
    ID3NoHeaderError = Exception  # type: ignore
    MP3 = None  # type: ignore
    OggVorbis = None  # type: ignore
    FLAC = None  # type: ignore
    WAVE = None  # type: ignore

from .base_registry import BaseRegistry
from .provenance_registry import ProvenanceRegistry

LOGGER = logging.getLogger(__name__)
PROVENANCE_TAG = "comfyvn_provenance"


class AssetRegistry(BaseRegistry):
    TABLE = "assets_registry"
    ASSETS_ROOT = Path("data/assets")
    META_ROOT = ASSETS_ROOT / "_meta"
    THUMB_ROOT = thumb_cache_dir()
    SIDECAR_SUFFIX = ".asset.json"
    _IMAGE_SUFFIXES = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
    }
    _AUDIO_WAVEFORM_SUFFIXES = {".wav", ".wave"}
    THUMB_SIZES = (256, 512)
    _thumb_executor: ThreadPoolExecutor | None = None
    _thumb_executor_lock = threading.Lock()
    _pending_futures: set[Future] = set()
    _pending_lock = threading.Lock()
    HOOK_ASSET_REGISTERED = "asset_registered"
    HOOK_ASSET_META_UPDATED = "asset_meta_updated"
    HOOK_ASSET_REMOVED = "asset_removed"
    HOOK_SIDECAR_WRITTEN = "asset_sidecar_written"
    _HOOK_EVENTS = (
        HOOK_ASSET_REGISTERED,
        HOOK_ASSET_META_UPDATED,
        HOOK_ASSET_REMOVED,
        HOOK_SIDECAR_WRITTEN,
    )

    def __init__(
        self,
        *args,
        assets_root: Path | str | None = None,
        thumb_root: Path | str | None = None,
        meta_root: Path | str | None = None,
        sidecar_suffix: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.ASSETS_ROOT = self._resolve_assets_root(assets_root)
        self.META_ROOT = self._resolve_meta_root(meta_root)
        self.THUMB_ROOT = self._resolve_thumb_root(thumb_root)
        self.sidecar_suffix = sidecar_suffix or self.SIDECAR_SUFFIX
        rel_hint = os.getenv("COMFYVN_THUMBS_REL")
        self._thumb_rel_base = (
            Path(rel_hint).expanduser() if rel_hint else Path("cache/thumbs")
        )
        self.ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
        if self.META_ROOT:
            self.META_ROOT.mkdir(parents=True, exist_ok=True)
        self.THUMB_ROOT.mkdir(parents=True, exist_ok=True)
        self._provenance = ProvenanceRegistry(
            db_path=self.db_path, project_id=self.project_id
        )
        self._hooks: dict[str, list[Callable[[Dict[str, Any]], None]]] = {
            event: [] for event in self._HOOK_EVENTS
        }

    @classmethod
    def _resolve_assets_root(cls, override: Path | str | None) -> Path:
        if override:
            return Path(override).expanduser().resolve()
        env = os.getenv("COMFYVN_ASSETS_ROOT")
        if env:
            return Path(env).expanduser().resolve()
        candidates = [
            Path("data/assets"),
            Path("assets"),
            Path("comfyvn/data/assets"),
            cls.ASSETS_ROOT,
        ]
        for candidate in candidates:
            candidate = Path(candidate).expanduser()
            if candidate.exists():
                return candidate.resolve()
        return Path("assets").expanduser().resolve()

    def _resolve_meta_root(self, override: Path | str | None) -> Path | None:
        if override is False:  # type: ignore[truthy-function]
            return None
        if override:
            meta = Path(override).expanduser().resolve()
            meta.mkdir(parents=True, exist_ok=True)
            return meta
        # keep legacy _meta directory for callers that still rely on it
        legacy = self.ASSETS_ROOT / "_meta"
        return legacy

    @staticmethod
    def _resolve_thumb_root(override: Path | str | None) -> Path:
        if override:
            return Path(override).expanduser().resolve()
        env = os.getenv("COMFYVN_THUMBS_ROOT")
        if env:
            return Path(env).expanduser().resolve()
        repo_cache = Path("cache/thumbs")
        if repo_cache.exists() or repo_cache.parent.exists():
            return repo_cache.expanduser().resolve()
        return thumb_cache_dir()

    def _ensure_schema(self) -> None:
        super()._ensure_schema()
        with self.connection() as conn:
            info = conn.execute("PRAGMA table_info(assets_registry)").fetchall()
            existing_columns = {row[1] for row in info}
            if not existing_columns:
                self._create_assets_table(conn)
            elif {"uid", "path_full", "meta"}.issubset(existing_columns):
                return
            else:
                LOGGER.info("Migrating legacy assets_registry schema")
                self._migrate_legacy_assets_table(conn, existing_columns)

    @staticmethod
    def _create_assets_table(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assets_registry (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                uid TEXT UNIQUE,
                type TEXT,
                path_full TEXT,
                path_thumb TEXT,
                hash TEXT,
                bytes INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                meta JSON
            )
            """
        )

    def _migrate_legacy_assets_table(
        self, conn: sqlite3.Connection, existing_columns: set[str]
    ) -> None:
        conn.execute("ALTER TABLE assets_registry RENAME TO assets_registry_legacy")
        self._create_assets_table(conn)
        select_meta = "meta_json" if "meta_json" in existing_columns else "meta"
        select_path = "path_full" if "path_full" in existing_columns else "path"
        conn.execute(
            f"""
            INSERT INTO assets_registry (
                id,
                project_id,
                uid,
                type,
                path_full,
                path_thumb,
                hash,
                bytes,
                meta,
                created_at
            )
            SELECT
                id,
                'default' AS project_id,
                CASE
                    WHEN hash IS NOT NULL AND length(hash) >= 16 THEN substr(hash, 1, 16)
                    ELSE printf('legacy_%s', id)
                END AS uid,
                type,
                {select_path} AS path_full,
                NULL AS path_thumb,
                hash,
                bytes,
                COALESCE({select_meta}, '{{}}') AS meta,
                created_at
            FROM assets_registry_legacy
            """
        )
        conn.execute("DROP TABLE assets_registry_legacy")

    # ---------------------
    # Public query helpers
    # ---------------------
    def list_assets(
        self,
        asset_type: Optional[str] = None,
        *,
        hash_value: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        text: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        select_cols = (
            "id, uid, type, path_full, path_thumb, hash, bytes, meta, created_at"
        )
        if asset_type:
            rows = self.fetchall(
                f"SELECT {select_cols} "
                f"FROM {self.TABLE} WHERE project_id = ? AND type = ? ORDER BY id DESC",
                [self.project_id, asset_type],
            )
        else:
            rows = self.fetchall(
                f"SELECT {select_cols} "
                f"FROM {self.TABLE} WHERE project_id = ? ORDER BY id DESC",
                [self.project_id],
            )
        assets = [self._format_asset_row(row) for row in rows]

        if hash_value:
            target_hash = str(hash_value).strip().lower()
            assets = [
                asset
                for asset in assets
                if str(asset.get("hash") or "").strip().lower() == target_hash
            ]

        if tags:
            requested = {str(tag).strip().lower() for tag in tags if str(tag).strip()}
            if requested:
                filtered: List[Dict[str, Any]] = []
                for asset in assets:
                    meta_raw = asset.get("meta")
                    meta = meta_raw if isinstance(meta_raw, dict) else {}
                    tag_values: Iterable[str] = meta.get("tags") or []
                    normalized = {str(t).strip().lower() for t in tag_values if t}
                    if requested.issubset(normalized):
                        filtered.append(asset)
                assets = filtered

        if text:
            needle = str(text).strip().lower()

            def _matches(candidate: Dict[str, Any]) -> bool:
                if needle in str(candidate.get("path") or "").lower():
                    return True
                meta_payload = candidate.get("meta") or {}
                if isinstance(meta_payload, dict):
                    for value in meta_payload.values():
                        if isinstance(value, str) and needle in value.lower():
                            return True
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, str) and needle in item.lower():
                                    return True
                return False

            assets = [asset for asset in assets if _matches(asset)]

        if limit is not None and limit >= 0:
            assets = assets[:limit]

        return assets

    def get_asset(self, uid: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta, created_at "
            f"FROM {self.TABLE} WHERE project_id = ? AND uid = ?",
            [self.project_id, uid],
        )
        return self._format_asset_row(row) if row else None

    def resolve_thumbnail_path(self, asset: Dict[str, Any] | str) -> Optional[Path]:
        """Resolve the on-disk thumbnail path for an asset, if available."""

        if isinstance(asset, str):
            record = self.get_asset(asset)
            if record is None:
                return None
        else:
            record = asset
        thumb_rel = record.get("thumb") if isinstance(record, dict) else None
        if not thumb_rel:
            return None
        try:
            thumb_name = Path(str(thumb_rel)).name
        except Exception:
            return None
        candidate = (self.THUMB_ROOT / thumb_name).resolve()
        return candidate if candidate.exists() else None

    # ---------------------
    # Hook management
    # ---------------------
    def add_hook(self, event: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register ``callback`` for a supported registry event."""

        if event not in self._hooks:
            raise ValueError(f"Unsupported asset registry hook: {event}")
        listeners = self._hooks[event]
        if callback not in listeners:
            listeners.append(callback)

    def remove_hook(
        self, event: str, callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Detach ``callback`` from the registry event list."""

        listeners = self._hooks.get(event)
        if not listeners:
            return
        try:
            listeners.remove(callback)
        except ValueError:
            return

    def iter_hooks(self, event: Optional[str] = None) -> Dict[str, tuple]:
        """Return a snapshot of registered hooks for debugging."""

        if event:
            if event not in self._hooks:
                raise ValueError(f"Unsupported asset registry hook: {event}")
            return {event: tuple(self._hooks[event])}
        return {name: tuple(callbacks) for name, callbacks in self._hooks.items()}

    def _emit_hook(self, event: str, payload: Dict[str, Any]) -> None:
        listeners = list(self._hooks.get(event, ()))
        for callback in listeners:
            try:
                callback(dict(payload))
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning(
                    "AssetRegistry hook %s failed via %s: %s", event, callback, exc
                )
        modder_event_map = {
            self.HOOK_ASSET_REGISTERED: (
                "on_asset_saved",
                "on_asset_registered",
            ),
            self.HOOK_ASSET_META_UPDATED: ("on_asset_meta_updated",),
            self.HOOK_ASSET_REMOVED: ("on_asset_removed",),
            self.HOOK_SIDECAR_WRITTEN: ("on_asset_sidecar_written",),
        }
        modder_targets = modder_event_map.get(event)
        if modder_targets:
            bridge_payload = dict(payload)
            bridge_payload.setdefault("hook_event", event)
            bridge_payload.setdefault("timestamp", time.time())
            for modder_event in modder_targets:
                try:
                    modder_hooks.emit(modder_event, dict(bridge_payload))
                except Exception:
                    LOGGER.debug(
                        "Modder hook emit failed for asset event %s -> %s",
                        event,
                        modder_event,
                        exc_info=True,
                    )

    def sidecar_path(self, uid: str) -> Optional[Path]:
        """Return the resolved sidecar path for ``uid`` if the asset exists."""

        asset = self.get_asset(uid)
        if asset is None:
            return None
        rel_path = Path(asset["path"])
        return self._sidecar_path(rel_path)

    def read_sidecar(self, uid: str) -> Dict[str, Any]:
        """Read and return the JSON payload stored in the asset sidecar."""

        asset = self.get_asset(uid)
        if asset is None:
            raise KeyError(f"Unknown asset uid: {uid}")
        sidecar_path = self.sidecar_path(uid)
        if sidecar_path is None or not sidecar_path.exists():
            raise FileNotFoundError(f"Sidecar missing for uid: {uid}")
        with sidecar_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def update_asset_meta(self, uid: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a new metadata payload for ``uid`` and rewrite its sidecar."""

        asset = self.get_asset(uid)
        if asset is None:
            raise KeyError(f"Unknown asset uid: {uid}")
        return self._save_asset_meta(asset, meta)

    def bulk_update_tags(
        self,
        uids: Sequence[str],
        *,
        add_tags: Iterable[str] | None = None,
        remove_tags: Iterable[str] | None = None,
        license_tag: str | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Update tag collections (and optional license) for a set of assets."""

        add_list = list(add_tags or [])
        remove_keys = {str(tag).strip().lower() for tag in (remove_tags or []) if tag}
        results: Dict[str, Dict[str, Any]] = {}
        for uid in uids:
            asset = self.get_asset(uid)
            if asset is None:
                LOGGER.warning("bulk_update_tags skipping unknown asset %s", uid)
                continue
            meta_payload = dict(asset.get("meta") or {})
            tags = meta_payload.get("tags")
            if not isinstance(tags, list):
                tags = []
            normalized = self._normalise_tags(tags)
            existing_keys = {t.lower() for t in normalized}
            if add_list:
                for tag in add_list:
                    candidate = str(tag).strip()
                    if not candidate:
                        continue
                    key = candidate.lower()
                    if key not in existing_keys:
                        normalized.append(candidate)
                        existing_keys.add(key)
            if remove_keys:
                normalized = [t for t in normalized if t.lower() not in remove_keys]
                existing_keys = {t.lower() for t in normalized}
            meta_payload["tags"] = normalized
            if license_tag is not None:
                if license_tag:
                    meta_payload["license"] = license_tag
                else:
                    meta_payload.pop("license", None)
            results[uid] = self._save_asset_meta(asset, meta_payload)
        return results

    def ensure_sidecar(self, uid: str, *, overwrite: bool = False) -> Path:
        """Ensure the sidecar file representing ``uid`` exists on disk."""

        asset = self.get_asset(uid)
        if asset is None:
            raise KeyError(f"Unknown asset uid: {uid}")
        rel_path = Path(asset["path"])
        sidecar_path = self._sidecar_path(rel_path)
        if sidecar_path.exists() and not overwrite:
            return sidecar_path
        meta_payload = self._prepare_metadata(dict(asset.get("meta") or {}))
        asset_snapshot = dict(asset)
        asset_snapshot["meta"] = meta_payload
        payload = self._compose_sidecar_payload(asset_snapshot)
        self._write_sidecar(rel_path, payload)
        sidecar_path = self._sidecar_path(rel_path)
        try:
            sidecar_rel = sidecar_path.relative_to(self.ASSETS_ROOT).as_posix()
        except ValueError:
            sidecar_rel = sidecar_path.as_posix()
        self._emit_hook(
            self.HOOK_ASSET_META_UPDATED,
            {
                "uid": uid,
                "type": asset.get("type"),
                "meta": meta_payload,
                "path": asset["path"],
                "sidecar": sidecar_rel,
            },
        )
        return sidecar_path

    # ---------------------
    # Registration helpers
    # ---------------------
    def register_file(
        self,
        source_path: Path | str,
        asset_type: str,
        *,
        dest_relative: Optional[Path | str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        copy: bool = True,
        provenance: Optional[Dict[str, Any]] = None,
        license_tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Copy (or reference) a file into the assets directory and index it."""
        source = Path(source_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Asset source does not exist: {source}")

        if dest_relative:
            rel_path = Path(dest_relative)
            if rel_path.is_absolute():
                raise ValueError("dest_relative must be relative to the assets root.")
        else:
            rel_path = Path(asset_type) / source.name

        dest = (self.ASSETS_ROOT / rel_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        if not copy:
            try:
                rel_path = source.relative_to(self.ASSETS_ROOT)
            except ValueError as exc:
                raise ValueError(
                    f"Non-copied assets must reside inside the assets root ({self.ASSETS_ROOT}); got {source}"
                ) from exc
            dest = source

        hash_source = source if copy else dest
        size_bytes = hash_source.stat().st_size
        file_hash = self._sha256(hash_source)
        uid = file_hash[:16]

        meta_updates = metadata.copy() if metadata else {}
        if license_tag:
            meta_updates.setdefault("license", license_tag)

        existing = self.get_asset(uid)
        if existing:
            merged_meta = self._merge_metadata(existing.get("meta") or {}, meta_updates)
            normalized_meta = self._save_asset_meta(existing, merged_meta)
            provenance_record = None
            asset_db_id = existing.get("id")
            if provenance and isinstance(asset_db_id, int):
                provenance_record = self._record_provenance(
                    asset_db_id,
                    uid,
                    file_hash,
                    provenance,
                    normalized_meta,
                )
                existing_path = self.resolve_path(uid)
                if existing_path and provenance_record:
                    self._embed_provenance_marker(existing_path, provenance_record)
                asset_snapshot = self.get_asset(uid) or existing
                payload = self._compose_sidecar_payload(
                    asset_snapshot, provenance=provenance_record
                )
                rel_existing = Path(asset_snapshot["path"])
                self._write_sidecar(rel_existing, payload)
            else:
                asset_snapshot = self.get_asset(uid) or existing
            LOGGER.info("Reused existing asset %s (%s)", uid, asset_snapshot["path"])
            response = dict(asset_snapshot)
            response["hash"] = file_hash
            if isinstance(response.get("meta"), dict):
                response["preview"] = response["meta"].get("preview")
            if provenance and provenance_record is None:
                LOGGER.warning(
                    "Provenance payload supplied but primary key missing for uid=%s",
                    uid,
                )
            if provenance_record:
                response["provenance"] = provenance_record
            return response

        if copy:
            if source != dest:
                shutil.copy2(source, dest)
                LOGGER.debug("Copied asset %s -> %s", source, dest)
            else:
                LOGGER.debug(
                    "Source and destination are identical for %s; skipping copy.",
                    source,
                )
                copy = False

        size_bytes = dest.stat().st_size
        preview_rel, _preview_kind, preview_payload = self._schedule_preview(dest, uid)
        meta_payload = dict(meta_updates)
        if preview_payload:
            meta_payload.setdefault("preview", preview_payload)
            paths = preview_payload.get("paths")
            if isinstance(paths, dict) and paths:
                meta_payload.setdefault("thumbnails", dict(paths))
        prepared_meta = self._prepare_metadata(meta_payload)
        meta_json = self.dumps(prepared_meta)
        preview_primary = preview_rel
        if preview_payload:
            preview_primary = (
                preview_payload.get("default")
                or preview_payload.get("path")
                or preview_primary
            )

        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO assets_registry (project_id, uid, type, path_full, path_thumb, hash, bytes, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self.project_id,
                    uid,
                    asset_type,
                    str(rel_path.as_posix()),
                    preview_primary,
                    file_hash,
                    size_bytes,
                    meta_json,
                ),
            )

        asset_row = self.fetchone(
            f"SELECT id FROM {self.TABLE} WHERE project_id = ? AND uid = ?",
            [self.project_id, uid],
        )
        asset_db_id = int(asset_row["id"]) if asset_row else None

        provenance_record = None
        if provenance and asset_db_id is not None:
            provenance_record = self._record_provenance(
                asset_db_id,
                uid,
                file_hash,
                provenance,
                prepared_meta,
            )
            if copy:
                self._embed_provenance_marker(dest, provenance_record)
        elif provenance:
            LOGGER.warning(
                "Provenance payload supplied but asset id unavailable for uid=%s", uid
            )

        asset_snapshot = self.get_asset(uid)
        if not asset_snapshot:
            raise RuntimeError(f"Asset {uid} failed to register in the database.")
        rel_path = Path(asset_snapshot["path"])
        payload = self._compose_sidecar_payload(
            asset_snapshot, provenance=provenance_record
        )
        self._write_sidecar(rel_path, payload)
        LOGGER.info("Registered asset %s (%s)", uid, rel_path)
        sidecar_path = self._sidecar_path(rel_path)
        try:
            sidecar_rel = str(sidecar_path.relative_to(self.ASSETS_ROOT).as_posix())
        except ValueError:
            sidecar_rel = sidecar_path.as_posix()
        self._emit_hook(
            self.HOOK_ASSET_REGISTERED,
            {
                "uid": uid,
                "type": asset_type,
                "path": asset_snapshot["path"],
                "meta": prepared_meta,
                "sidecar": sidecar_rel,
                "bytes": size_bytes,
            },
        )
        response = dict(asset_snapshot)
        response["hash"] = file_hash
        if isinstance(response.get("meta"), dict):
            response["preview"] = response["meta"].get("preview")
        if provenance_record:
            response["provenance"] = provenance_record
        response["sidecar"] = sidecar_rel
        return response

    def resolve_path(self, uid: str) -> Optional[Path]:
        asset = self.get_asset(uid)
        if not asset:
            return None
        return (self.ASSETS_ROOT / asset["path"]).resolve()

    def remove_asset(self, uid: str, *, delete_files: bool = False) -> bool:
        """Delete an asset registry entry and optionally remove files on disk."""
        asset = self.get_asset(uid)
        if not asset:
            return False

        with self.connection() as conn:
            conn.execute(
                f"DELETE FROM {self.TABLE} WHERE project_id = ? AND uid = ?",
                (self.project_id, uid),
            )

        thumb_rel = asset.get("thumb")
        if thumb_rel:
            try:
                full_thumb = (self.THUMB_ROOT / Path(thumb_rel).name).resolve()
                if full_thumb.exists():
                    full_thumb.unlink()
            except Exception:
                LOGGER.debug("Failed to remove thumbnail for %s", uid)

        if delete_files:
            try:
                path = (self.ASSETS_ROOT / asset["path"]).resolve()
                if path.exists():
                    path.unlink()
            except Exception:
                LOGGER.debug("Failed to remove asset file for %s", uid)

        rel_path = Path(asset["path"])
        primary_sidecar = self._sidecar_path(rel_path)
        if primary_sidecar.exists():
            try:
                primary_sidecar.unlink()
            except Exception:
                LOGGER.debug("Failed to remove sidecar for %s", uid)
        if self.META_ROOT:
            legacy_sidecar = (self.META_ROOT / rel_path).with_suffix(".json")
            if legacy_sidecar.exists():
                try:
                    legacy_sidecar.unlink()
                except Exception:
                    LOGGER.debug("Failed to remove legacy sidecar for %s", uid)

        try:
            sidecar_rel = primary_sidecar.relative_to(self.ASSETS_ROOT).as_posix()
        except Exception:
            sidecar_rel = primary_sidecar.as_posix()
        meta_payload: Dict[str, Any]
        raw_meta = asset.get("meta")
        if isinstance(raw_meta, dict):
            meta_payload = dict(raw_meta)
        elif raw_meta is None:
            meta_payload = {}
        else:
            meta_payload = {"raw": raw_meta}

        LOGGER.info("Removed asset %s", uid)
        self._emit_hook(
            self.HOOK_ASSET_REMOVED,
            {
                "uid": uid,
                "type": asset.get("type"),
                "path": asset["path"],
                "sidecar": sidecar_rel,
                "meta": meta_payload,
                "bytes": asset.get("bytes"),
            },
        )
        return True

    # ---------------------
    # Internal helpers
    # ---------------------
    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _sidecar_path(self, rel_path: Path) -> Path:
        rel = Path(rel_path)
        target = self.ASSETS_ROOT / rel
        return target.with_suffix(target.suffix + self.sidecar_suffix)

    def _write_sidecar(self, rel_path: Path, payload: Dict[str, Any]) -> None:
        canonical = dict(payload)
        canonical.setdefault("id", canonical.get("uid"))
        primary_path = self._sidecar_path(rel_path)
        primary_path.parent.mkdir(parents=True, exist_ok=True)
        primary_path.write_text(
            json.dumps(canonical, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        LOGGER.debug("Sidecar written: %s", primary_path)
        if self.META_ROOT:
            legacy_path = (self.META_ROOT / rel_path).with_suffix(".json")
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_text(
                json.dumps(canonical, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            LOGGER.debug("Legacy sidecar mirrored: %s", legacy_path)
        self._emit_hook(
            self.HOOK_SIDECAR_WRITTEN,
            {
                "uid": canonical.get("uid"),
                "type": canonical.get("type"),
                "sidecar": str(primary_path),
                "rel_path": rel_path.as_posix(),
            },
        )

    def _format_asset_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        payload = dict(row)
        payload["path"] = payload.pop("path_full")
        thumb = payload.pop("path_thumb", None)
        if thumb is not None:
            payload["thumb"] = thumb
        meta = payload.get("meta")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {"raw": meta}
        if meta is None:
            meta = {}
        prepared_meta = self._prepare_metadata(meta)
        payload["meta"] = prepared_meta
        if "preview" in prepared_meta and isinstance(prepared_meta["preview"], dict):
            preview_snapshot = dict(prepared_meta["preview"])
        elif thumb:
            preview_snapshot = {
                "kind": (
                    "waveform" if str(thumb).lower().endswith(".json") else "thumbnail"
                ),
                "path": thumb,
            }
            prepared_meta.setdefault("preview", preview_snapshot)
        else:
            preview_snapshot = None
        thumb_map = prepared_meta.get("thumbnails")
        if isinstance(thumb_map, dict):
            prepared_meta["thumbnails"] = dict(thumb_map)
            if preview_snapshot is not None:
                preview_snapshot.setdefault("paths", dict(thumb_map))
                if "default" not in preview_snapshot and thumb_map:
                    try:
                        first_key = next(iter(sorted(thumb_map)))
                        preview_snapshot["default"] = thumb_map[first_key]
                    except StopIteration:
                        pass
        rel_path = Path(payload["path"])
        sidecar_path = self._sidecar_path(rel_path)
        try:
            sidecar_rel = sidecar_path.relative_to(self.ASSETS_ROOT)
            payload["sidecar"] = sidecar_rel.as_posix()
        except Exception:
            payload["sidecar"] = sidecar_path.as_posix()
        links: Dict[str, Any] = {
            "file": payload["path"],
            "sidecar": payload["sidecar"],
        }
        if thumb:
            links["thumbnail"] = thumb
        if preview_snapshot:
            if "paths" in preview_snapshot:
                links["thumbnails"] = dict(preview_snapshot["paths"])
            elif preview_snapshot.get("path"):
                links["preview"] = preview_snapshot["path"]
        payload["links"] = links
        created = payload.pop("created_at", None)
        if created is not None:
            payload["created_at"] = created
        return payload

    @staticmethod
    def _normalise_tags(tags: Iterable[Any]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for tag in tags:
            text = str(tag).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(text)
        return ordered

    def _prepare_metadata(self, meta_payload: Dict[str, Any] | None) -> Dict[str, Any]:
        """Normalise metadata for persistence and sidecar emission."""

        meta: Dict[str, Any] = dict(meta_payload or {})
        tags = meta.get("tags")
        if isinstance(tags, list):
            meta["tags"] = self._normalise_tags(tags)
        elif tags in (None, "", []):
            meta["tags"] = []
        else:
            meta["tags"] = self._normalise_tags([tags])

        license_tag = meta.get("license")
        if isinstance(license_tag, str):
            meta["license"] = license_tag.strip() or None
        elif license_tag is not None:
            meta["license"] = str(license_tag)

        origin = meta.get("origin")
        if origin is not None:
            meta["origin"] = str(origin)

        version = meta.get("version")
        if version is None:
            meta["version"] = 1
        else:
            try:
                meta["version"] = int(version)
            except (TypeError, ValueError):
                meta["version"] = 1

        return meta

    def _merge_metadata(
        self, existing: Dict[str, Any], updates: Dict[str, Any] | None
    ) -> Dict[str, Any]:
        """Merge ``updates`` into ``existing`` preserving tag uniqueness."""

        merged: Dict[str, Any] = dict(existing or {})
        if not updates:
            return merged

        for key, value in updates.items():
            if key == "tags":
                current = merged.get("tags")
                current_list = (
                    list(current)
                    if isinstance(current, list)
                    else [current] if current else []
                )
                update_list = (
                    list(value)
                    if isinstance(value, (list, tuple, set))
                    else [value] if value not in (None, "", []) else []
                )
                merged["tags"] = self._normalise_tags([*current_list, *update_list])
                continue
            if key == "license":
                merged["license"] = (
                    (value or None) if not isinstance(value, dict) else None
                )
                continue
            if key in {"preview", "thumbnails"} and isinstance(value, dict):
                merged[key] = dict(value)
                continue
            merged[key] = value

        return merged

    def _compose_sidecar_payload(
        self, asset: Dict[str, Any], *, provenance: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Compose a canonical sidecar payload for ``asset``."""

        meta_payload = self._prepare_metadata(dict(asset.get("meta") or {}))
        preview_payload: Dict[str, Any] | None = None

        preview_meta = meta_payload.get("preview")
        if isinstance(preview_meta, dict):
            preview_payload = dict(preview_meta)
        elif asset.get("thumb"):
            thumb = str(asset["thumb"])
            preview_payload = {
                "kind": "waveform" if thumb.lower().endswith(".json") else "thumbnail",
                "path": thumb,
            }

        thumb_map = meta_payload.get("thumbnails")
        if isinstance(thumb_map, dict):
            if preview_payload is None:
                preview_payload = {"kind": "thumbnail"}
            preview_payload["paths"] = dict(thumb_map)
            default_thumb = preview_payload.get("default")
            if not default_thumb and thumb_map:
                try:
                    first_key = next(iter(sorted(thumb_map)))
                    preview_payload["default"] = thumb_map[first_key]
                except StopIteration:
                    pass

        payload: Dict[str, Any] = {
            "id": asset.get("uid"),
            "uid": asset.get("uid"),
            "type": asset.get("type"),
            "path": asset.get("path"),
            "hash": asset.get("hash"),
            "bytes": asset.get("bytes"),
            "tags": list(meta_payload.get("tags") or []),
            "license": meta_payload.get("license"),
            "origin": meta_payload.get("origin"),
            "version": meta_payload.get("version"),
            "created_at": asset.get("created_at"),
            "meta": meta_payload,
        }

        if preview_payload:
            payload["preview"] = preview_payload

        links = asset.get("links")
        if isinstance(links, dict) and links:
            payload["links"] = dict(links)

        if provenance:
            payload["provenance"] = dict(provenance)

        return payload

    def _save_asset_meta(
        self, asset: Dict[str, Any], meta_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        prepared_meta = self._prepare_metadata(meta_payload)
        meta_json = self.dumps(prepared_meta)
        with self.connection() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET meta = ? WHERE project_id = ? AND uid = ?",
                (meta_json, self.project_id, asset["uid"]),
            )

        rel_path = Path(asset["path"])
        asset_snapshot = dict(asset)
        asset_snapshot["meta"] = prepared_meta
        payload = self._compose_sidecar_payload(asset_snapshot)
        self._write_sidecar(rel_path, payload)
        sidecar_path = self._sidecar_path(rel_path)
        try:
            sidecar_rel = sidecar_path.relative_to(self.ASSETS_ROOT).as_posix()
        except ValueError:
            sidecar_rel = sidecar_path.as_posix()
        self._emit_hook(
            self.HOOK_ASSET_META_UPDATED,
            {
                "uid": asset["uid"],
                "type": asset.get("type"),
                "meta": prepared_meta,
                "path": asset["path"],
                "sidecar": sidecar_rel,
            },
        )
        return prepared_meta

    @classmethod
    def _get_thumbnail_executor(cls) -> ThreadPoolExecutor:
        if cls._thumb_executor is None:
            with cls._thumb_executor_lock:
                if cls._thumb_executor is None:
                    cls._thumb_executor = ThreadPoolExecutor(
                        max_workers=2,
                        thread_name_prefix="AssetThumb",
                    )
        return cls._thumb_executor

    def _schedule_preview(
        self, dest: Path, uid: str
    ) -> tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
        suffix = dest.suffix.lower()
        preview_kind: Optional[str]
        if suffix in self._IMAGE_SUFFIXES:
            if Image is None:
                LOGGER.debug("Pillow not available; skipping thumbnail for %s", dest)
                return (None, None, None)
            preview_kind = "thumbnail"
            thumb_paths: Dict[str, str] = {}
            primary_rel: Optional[str] = None
            executor = self._get_thumbnail_executor()
            for index, size in enumerate(self.THUMB_SIZES):
                thumb_path = self.THUMB_ROOT / f"{uid}_{size}{suffix}"
                thumb_rel = str((self._thumb_rel_base / thumb_path.name).as_posix())
                thumb_paths[str(size)] = thumb_rel
                primary_rel = primary_rel or thumb_rel
                future = executor.submit(
                    self._thumbnail_job,
                    dest,
                    thumb_path,
                    thumb_rel,
                    uid,
                    preview_kind,
                    size,
                    primary=index == 0,
                )
                self._register_thumbnail_future(future)
            preview_payload = {
                "kind": preview_kind,
                "paths": thumb_paths,
                "default": primary_rel,
            }
            return primary_rel, preview_kind, preview_payload
        if suffix in self._AUDIO_WAVEFORM_SUFFIXES:
            thumb_path = self.THUMB_ROOT / f"{uid}.waveform.json"
            thumb_rel = str((self._thumb_rel_base / thumb_path.name).as_posix())
            preview_kind = "waveform"
            executor = self._get_thumbnail_executor()
            future = executor.submit(
                self._thumbnail_job,
                dest,
                thumb_path,
                thumb_rel,
                uid,
                preview_kind,
                None,
                primary=True,
            )
            self._register_thumbnail_future(future)
            preview_payload = {"kind": preview_kind, "path": thumb_rel}
            return thumb_rel, preview_kind, preview_payload
        LOGGER.debug("Skipping preview for %s (unsupported suffix)", dest)
        return (None, None, None)

    @classmethod
    def _register_thumbnail_future(cls, future: Future) -> None:
        with cls._pending_lock:
            cls._pending_futures.add(future)

        def _cleanup(fut: Future) -> None:
            with cls._pending_lock:
                cls._pending_futures.discard(fut)

        future.add_done_callback(_cleanup)

    @classmethod
    def wait_for_thumbnails(cls, timeout: float | None = None) -> bool:
        with cls._pending_lock:
            pending = list(cls._pending_futures)
        if not pending:
            return True
        done, not_done = wait(pending, timeout=timeout)
        return not not_done

    def _thumbnail_job(
        self,
        source: Path,
        thumb_path: Path,
        thumb_rel: str,
        uid: str,
        preview_kind: Optional[str],
        thumb_size: Optional[int],
        *,
        primary: bool,
    ) -> None:
        success = self._create_preview_file(source, thumb_path, thumb_size=thumb_size)
        if not success:
            LOGGER.warning(
                "Clearing %s preview for %s due to generation failure",
                preview_kind or "thumbnail",
                uid,
            )
            thumb_path.unlink(missing_ok=True)
            if primary:
                with self.connection() as conn:
                    conn.execute(
                        f"UPDATE {self.TABLE} SET path_thumb = NULL WHERE project_id = ? AND uid = ?",
                        (self.project_id, uid),
                    )

    def _create_preview_file(
        self, source: Path, thumb_path: Path, *, thumb_size: Optional[int]
    ) -> bool:
        suffix = source.suffix.lower()
        if suffix in self._IMAGE_SUFFIXES:
            return self._create_image_thumbnail(source, thumb_path, thumb_size)
        if suffix in self._AUDIO_WAVEFORM_SUFFIXES:
            return self._create_waveform_preview(source, thumb_path)
        return False

    @staticmethod
    def _create_image_thumbnail(
        source: Path, thumb_path: Path, thumb_size: Optional[int]
    ) -> bool:
        if Image is None:
            return False
        try:
            with Image.open(source) as img:  # type: ignore[attr-defined]
                size = int(thumb_size or 256)
                img.thumbnail((size, size))
                thumb_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(thumb_path)
            return True
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Thumbnail generation failed for %s: %s", source, exc)
            return False

    @staticmethod
    def _create_waveform_preview(source: Path, thumb_path: Path) -> bool:
        try:
            with wave.open(str(source), "rb") as wav_file:
                frames = wav_file.getnframes()
                channels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                if frames <= 0 or sampwidth not in (1, 2):
                    LOGGER.debug("Unsupported waveform parameters for %s", source)
                    return False
                raw = wav_file.readframes(frames)
        except wave.Error as exc:
            LOGGER.debug("Waveform probe failed for %s: %s", source, exc)
            return False
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Waveform read failed for %s: %s", source, exc)
            return False

        if sampwidth == 1:
            samples = array("b", raw)
        else:
            samples = array("h")
            samples.frombytes(raw)

        if channels > 1:
            samples = samples[::channels]

        if not samples:
            LOGGER.debug("No samples available for waveform preview in %s", source)
            return False

        max_amplitude = max(1, max(abs(int(v)) for v in samples))
        target_points = 512
        step = max(1, len(samples) // target_points)
        points: List[float] = []
        for idx in range(0, len(samples), step):
            window = samples[idx : idx + step]
            if not window:
                break
            peak = max(window)
            trough = min(window)
            amplitude = max(abs(int(peak)), abs(int(trough))) / max_amplitude
            points.append(round(float(amplitude), 4))
            if len(points) >= target_points:
                break

        payload = {
            "kind": "waveform",
            "channels": channels,
            "sample_rate": framerate,
            "points": points,
        }
        try:
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return True
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to write waveform preview for %s: %s", source, exc)
            return False

    # ---------------------
    # Provenance helpers
    # ---------------------
    def _record_provenance(
        self,
        asset_db_id: int,
        uid: str,
        file_hash: str,
        provenance: Dict[str, Any],
        meta_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        source = (
            provenance.get("source") or meta_payload.get("source") or "unspecified"
        ).strip()
        user_id = (
            provenance.get("user_id")
            or meta_payload.get("user_id")
            or os.getenv("COMFYVN_USER")
        )
        workflow_hash = provenance.get("workflow_hash")
        commit_hash = provenance.get("commit_hash") or os.getenv("COMFYVN_GIT_COMMIT")
        inputs = provenance.get("inputs") or {}
        inputs.setdefault("asset_uid", uid)
        inputs.setdefault("asset_hash", file_hash)
        c2pa_like = provenance.get("c2pa_like") or {}

        record = self._provenance.record(
            asset_db_id,
            source=source,
            workflow_hash=workflow_hash,
            commit_hash=commit_hash,
            inputs=inputs,
            c2pa_like=c2pa_like,
            user_id=user_id,
        )
        record["asset_uid"] = uid
        return record

    def _embed_provenance_marker(
        self, dest: Path, provenance_record: Dict[str, Any]
    ) -> None:
        if Image is None:
            LOGGER.debug("Skipping provenance stamp for %s (Pillow unavailable)", dest)
            return

        marker = json.dumps(
            {
                "provenance_id": provenance_record.get("id"),
                "source": provenance_record.get("source"),
                "workflow_hash": provenance_record.get("workflow_hash"),
                "created_at": provenance_record.get("created_at"),
            },
            ensure_ascii=False,
        )

        suffix = dest.suffix.lower()
        try:
            if suffix == ".png" and PngImagePlugin is not None:
                self._stamp_png(dest, marker)
            elif suffix in {".mp3", ".ogg", ".oga", ".flac", ".wav", ".wave"}:
                self._stamp_audio(dest, marker, suffix)
            else:
                LOGGER.debug("No provenance marker implementation for %s files", suffix)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to embed provenance marker for %s: %s", dest, exc)

    @staticmethod
    def _stamp_png(dest: Path, marker: str) -> None:
        if Image is None or PngImagePlugin is None:
            return
        with Image.open(dest) as img:  # type: ignore[attr-defined]
            png_info = PngImagePlugin.PngInfo()  # type: ignore[attr-defined]
            if hasattr(img, "text"):
                for key, value in getattr(img, "text").items():
                    png_info.add_text(key, value)
            else:
                for key, value in img.info.items():
                    if isinstance(value, str):
                        png_info.add_text(key, value)
            png_info.add_text(PROVENANCE_TAG, marker)
            img.save(dest, pnginfo=png_info)

    @staticmethod
    def _stamp_audio(dest: Path, marker: str, suffix: str) -> None:
        if suffix == ".mp3":
            AssetRegistry._stamp_mp3(dest, marker)
        elif suffix in {".ogg", ".oga"}:
            AssetRegistry._stamp_ogg(dest, marker)
        elif suffix == ".flac":
            AssetRegistry._stamp_flac(dest, marker)
        elif suffix in {".wav", ".wave"}:
            AssetRegistry._stamp_wav(dest, marker)

    @staticmethod
    def _stamp_mp3(dest: Path, marker: str) -> None:
        if MP3 is None or ID3 is None or TXXX is None:
            LOGGER.debug(
                "Mutagen ID3 support unavailable; skipping MP3 provenance for %s", dest
            )
            return
        try:
            try:
                tags = ID3(dest)  # type: ignore[call-arg]
            except ID3NoHeaderError:  # type: ignore[misc]
                tags = ID3()  # type: ignore[call-arg]
            tags.delall(f"TXXX:{PROVENANCE_TAG}")
            tags.add(TXXX(encoding=3, desc=PROVENANCE_TAG, text=[marker]))
            tags.save(dest)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Unable to embed MP3 provenance for %s: %s", dest, exc)

    @staticmethod
    def _stamp_ogg(dest: Path, marker: str) -> None:
        if OggVorbis is None:
            LOGGER.debug(
                "Mutagen Ogg support unavailable; skipping provenance for %s", dest
            )
            return
        try:
            audio = OggVorbis(dest)  # type: ignore[call-arg]
            audio[PROVENANCE_TAG] = [marker]
            audio.save()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Unable to embed OGG provenance for %s: %s", dest, exc)

    @staticmethod
    def _stamp_flac(dest: Path, marker: str) -> None:
        if FLAC is None:
            LOGGER.debug(
                "Mutagen FLAC support unavailable; skipping provenance for %s", dest
            )
            return
        try:
            audio = FLAC(dest)  # type: ignore[call-arg]
            audio[PROVENANCE_TAG] = [marker]
            audio.save()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Unable to embed FLAC provenance for %s: %s", dest, exc)

    @staticmethod
    def _stamp_wav(dest: Path, marker: str) -> None:
        if WAVE is None or TXXX is None:
            LOGGER.debug(
                "Mutagen WAV support unavailable; skipping provenance for %s", dest
            )
            return
        try:
            audio = WAVE(dest)  # type: ignore[call-arg]
            if getattr(audio, "tags", None) is None:
                add_tags = getattr(audio, "add_tags", None)
                if callable(add_tags):
                    add_tags()
            tags = getattr(audio, "tags", None)
            if tags is None:
                LOGGER.warning(
                    "Unable to embed WAV provenance for %s (no tag container)", dest
                )
                return
            tags.delall(f"TXXX:{PROVENANCE_TAG}")
            tags.add(TXXX(encoding=3, desc=PROVENANCE_TAG, text=[marker]))  # type: ignore[call-arg]
            audio.save()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Unable to embed WAV provenance for %s: %s", dest, exc)
