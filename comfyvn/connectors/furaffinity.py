from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from comfyvn.config import runtime_paths
from comfyvn.persona.schema import normalise_tags, slugify

LOGGER = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_EXTENSION_MAP = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


def _resolve_extension(filename: Optional[str], media_type: Optional[str]) -> str:
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in ALLOWED_EXTENSIONS:
            return ext
    if media_type:
        media = media_type.lower()
        if media in MEDIA_EXTENSION_MAP:
            return MEDIA_EXTENSION_MAP[media]
    return ".png"


def _ensure_folder(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)


def _decode_base64(data: str) -> bytes:
    payload = data.strip()
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")
    try:
        return base64.b64decode(payload, validate=True)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError("invalid base64 payload") from exc


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class FurAffinityUploadManager:
    """Handle user-supplied FurAffinity uploads (no scraping)."""

    def __init__(self, import_root: Optional[Path] = None) -> None:
        default_root = runtime_paths.data_dir("persona", "imports")
        self.import_root = Path(import_root or default_root)
        self.logger = LOGGER

    def _target_folder(self, persona_id: str) -> Path:
        persona_slug = slugify(persona_id or "pending")
        folder = Path(self.import_root) / persona_slug
        _ensure_folder(folder)
        return folder

    def store_upload(
        self,
        entry: Mapping[str, Any],
        persona_id: str,
        *,
        consent: Mapping[str, Any],
        allow_nsfw: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        data_field = entry.get("data") or entry.get("base64")
        if not isinstance(data_field, str) or not data_field.strip():
            raise ValueError("image payload missing base64 data")
        blob = _decode_base64(data_field)
        if not blob:
            raise ValueError("image payload decoded empty")

        sha = hashlib.sha256(blob).hexdigest()
        filename = entry.get("filename")
        media_type = entry.get("media_type")
        ext = _resolve_extension(filename, media_type)

        folder = self._target_folder(persona_id)
        stored_name = f"{sha}{ext}"
        target = folder / stored_name
        target.write_bytes(blob)

        timestamp = time.time()
        general_tags = normalise_tags(entry.get("tags"))
        nsfw_tags = normalise_tags(entry.get("nsfw_tags"))
        kept_nsfw: Iterable[str] = nsfw_tags if allow_nsfw else []
        trimmed_nsfw = list(nsfw_tags) if not allow_nsfw else []

        provenance: Dict[str, Any] = {}
        source_url = entry.get("source_url")
        if isinstance(source_url, str) and source_url.strip():
            provenance["source_url"] = source_url.strip()

        sidecar_payload = {
            "hash": sha,
            "persona_id": slugify(persona_id or "pending"),
            "created_at": timestamp,
            "size": len(blob),
            "filename": filename,
            "stored_name": stored_name,
            "media_type": media_type,
            "source": entry.get("source") or "upload",
            "rights": consent.get("rights"),
            "consent_sources": consent.get("sources"),
            "artist": entry.get("artist"),
            "title": entry.get("title"),
            "description": entry.get("description"),
            "tags": list(general_tags),
            "nsfw_tags": list(kept_nsfw),
            "nsfw_tags_trimmed": trimmed_nsfw,
            "provenance": provenance or None,
        }
        sidecar_path = target.with_suffix(target.suffix + ".meta.json")
        _write_json(sidecar_path, sidecar_payload)

        asset_record = {
            "hash": sha,
            "path": target.as_posix(),
            "sidecar": sidecar_path.as_posix(),
            "size": len(blob),
            "filename": filename or stored_name,
            "media_type": media_type,
            "created_at": timestamp,
            "tags": list(general_tags),
            "nsfw_tags": list(kept_nsfw),
        }

        debug = {
            "trimmed_nsfw_tags": trimmed_nsfw,
            "stored": stored_name,
        }
        return asset_record, debug

    def store_many(
        self,
        images: Iterable[Mapping[str, Any]],
        persona_id: str,
        *,
        consent: Mapping[str, Any],
        allow_nsfw: bool,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        stored: List[Dict[str, Any]] = []
        debug_entries: List[Dict[str, Any]] = []
        for entry in images:
            if not isinstance(entry, Mapping):
                raise ValueError("image entries must be objects")
            asset, debug = self.store_upload(
                entry,
                persona_id,
                consent=consent,
                allow_nsfw=allow_nsfw,
            )
            stored.append(asset)
            debug_entries.append(debug)
        return stored, debug_entries
