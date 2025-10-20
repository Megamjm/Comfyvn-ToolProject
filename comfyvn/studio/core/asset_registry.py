"""
Asset registry facade for the Studio shell.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # thumbnail generation optional
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - pillow optional
    Image = None  # type: ignore

from .base_registry import BaseRegistry

LOGGER = logging.getLogger(__name__)


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
        return [dict(row) for row in rows]

    def get_asset(self, uid: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
            f"FROM {self.TABLE} WHERE project_id = ? AND uid = ?",
            [self.project_id, uid],
        )
        return dict(row) if row else None

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
        meta_payload = metadata or {}
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

        sidecar = {
            "uid": uid,
            "type": asset_type,
            "path": str(rel_path.as_posix()),
            "hash": file_hash,
            "bytes": size_bytes,
            "meta": meta_payload,
        }
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
