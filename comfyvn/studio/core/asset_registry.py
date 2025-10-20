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
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # thumbnail generation optional
    from PIL import Image  # type: ignore
    from PIL import PngImagePlugin  # type: ignore
except Exception:  # pragma: no cover - pillow optional
    Image = None  # type: ignore
    PngImagePlugin = None  # type: ignore

from .base_registry import BaseRegistry
from .provenance_registry import ProvenanceRegistry

LOGGER = logging.getLogger(__name__)
PROVENANCE_TAG = "comfyvn_provenance"


class AssetRegistry(BaseRegistry):
    TABLE = "assets_registry"
    ASSETS_ROOT = Path("data/assets")
    META_ROOT = ASSETS_ROOT / "_meta"
    THUMB_ROOT = Path("cache/thumbs")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
        self.META_ROOT.mkdir(parents=True, exist_ok=True)
        self.THUMB_ROOT.mkdir(parents=True, exist_ok=True)
        self._provenance = ProvenanceRegistry(db_path=self.db_path, project_id=self.project_id)

    def _ensure_schema(self) -> None:
        super()._ensure_schema()
        with self.connection() as conn:
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

    # ---------------------
    # Public query helpers
    # ---------------------
    def list_assets(self, asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if asset_type:
            rows = self.fetchall(
                f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
                f"FROM {self.TABLE} WHERE project_id = ? AND type = ? ORDER BY id DESC",
                [self.project_id, asset_type],
            )
        else:
            rows = self.fetchall(
                f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
                f"FROM {self.TABLE} WHERE project_id = ? ORDER BY id DESC",
                [self.project_id],
            )
        return [self._format_asset_row(row) for row in rows]

    def get_asset(self, uid: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
            f"FROM {self.TABLE} WHERE project_id = ? AND uid = ?",
            [self.project_id, uid],
        )
        return self._format_asset_row(row) if row else None

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

        rel_path = Path(dest_relative) if dest_relative else Path(asset_type) / source.name
        dest = self.ASSETS_ROOT / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        if copy:
            shutil.copy2(source, dest)
            LOGGER.debug("Copied asset %s -> %s", source, dest)
        else:
            dest = source
            rel_path = dest.relative_to(self.ASSETS_ROOT)

        file_hash = self._sha256(dest)
        uid = file_hash[:16]
        meta_payload = metadata.copy() if metadata else {}
        if license_tag:
            meta_payload.setdefault("license", license_tag)
        size_bytes = dest.stat().st_size
        thumb_path = self._create_thumbnail(dest, uid)
        thumb_rel = str(thumb_path) if thumb_path else None

        meta_json = self.dumps(meta_payload)
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO assets_registry (project_id, uid, type, path_full, path_thumb, hash, bytes, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    type=excluded.type,
                    path_full=excluded.path_full,
                    path_thumb=excluded.path_thumb,
                    hash=excluded.hash,
                    bytes=excluded.bytes,
                    meta=excluded.meta
                """,
                (
                    self.project_id,
                    uid,
                    asset_type,
                    str(rel_path.as_posix()),
                    thumb_rel,
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
                meta_payload,
            )
            if copy:
                self._embed_provenance_marker(dest, provenance_record)
        elif provenance:
            LOGGER.warning("Provenance payload supplied but asset id unavailable for uid=%s", uid)

        sidecar = {
            "uid": uid,
            "type": asset_type,
            "path": str(rel_path.as_posix()),
            "hash": file_hash,
            "bytes": size_bytes,
            "meta": meta_payload,
        }
        if provenance_record:
            sidecar["provenance"] = provenance_record
        self._write_sidecar(rel_path, sidecar)
        LOGGER.info("Registered asset %s (%s)", uid, rel_path)
        return {
            "uid": uid,
            "type": asset_type,
            "path": str(rel_path.as_posix()),
            "thumb": thumb_rel,
            "hash": file_hash,
            "bytes": size_bytes,
            "meta": meta_payload,
            "provenance": provenance_record,
        }

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

        sidecar_path = (self.META_ROOT / Path(asset["path"])).with_suffix(".json")
        if sidecar_path.exists():
            try:
                sidecar_path.unlink()
            except Exception:
                LOGGER.debug("Failed to remove sidecar for %s", uid)

        LOGGER.info("Removed asset %s", uid)
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

    def _write_sidecar(self, rel_path: Path, payload: Dict[str, Any]) -> None:
        sidecar_path = (self.META_ROOT / rel_path).with_suffix(".json")
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.debug("Sidecar written: %s", sidecar_path)

    @staticmethod
    def _format_asset_row(row: sqlite3.Row) -> Dict[str, Any]:
        payload = dict(row)
        payload["path"] = payload.pop("path_full")
        thumb = payload.pop("path_thumb", None)
        if thumb is not None:
            payload["thumb"] = thumb
        meta = payload.get("meta")
        if isinstance(meta, str):
            try:
                payload["meta"] = json.loads(meta)
            except json.JSONDecodeError:
                payload["meta"] = meta
        return payload

    def _create_thumbnail(self, dest: Path, uid: str) -> Optional[str]:
        if Image is None:
            LOGGER.debug("Pillow not available; skipping thumbnail for %s", dest)
            return None
        try:
            thumb_path = self.THUMB_ROOT / f"{uid}{dest.suffix}"
            with Image.open(dest) as img:  # type: ignore[attr-defined]
                img.thumbnail((256, 256))
                img.save(thumb_path)
            return str(Path("cache/thumbs") / thumb_path.name)
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Thumbnail generation failed for %s: %s", dest, exc)
            return None

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
        source = (provenance.get("source") or meta_payload.get("source") or "unspecified").strip()
        user_id = provenance.get("user_id") or meta_payload.get("user_id") or os.getenv("COMFYVN_USER")
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

    def _embed_provenance_marker(self, dest: Path, provenance_record: Dict[str, Any]) -> None:
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
