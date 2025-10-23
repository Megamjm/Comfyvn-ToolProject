from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

LOGGER = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
EXPORTS_ROOT = ROOT / "exports" / "assets" / "worlds"
MANIFEST_NAME = "assets_index.json"

_SLUG_PATTERN = re.compile(r"^[a-z0-9\-]+$")
_WORLD_ID_PATTERN = re.compile(r"^[a-z0-9_\-]+$")
_TYPE_FOLDERS = {
    "portrait": "portraits",
    "sprite": "sprites",
    "background": "backgrounds",
    "ui": "ui",
    "audio": "audio",
    "fx": "fx",
}

try:  # pillow optional
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - pillow optional
    Image = None  # type: ignore[misc]


class WorldAssetPipelineError(RuntimeError):
    """Raised when a pipeline asset cannot be written."""


def _normalise_slug(value: Optional[str], fallback: str) -> str:
    if not value:
        value = fallback
    value = value.lower()
    value = re.sub(r"[^a-z0-9\-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    value = value.strip("-")
    return value or fallback


def _ensure_slug(value: Optional[str], fallback: str) -> str:
    slug = _normalise_slug(value, fallback)
    if not _SLUG_PATTERN.fullmatch(slug):
        slug = _normalise_slug(slug, fallback)
    return slug or fallback


def _ensure_world_id(world_id: Optional[str]) -> str:
    if not world_id:
        raise WorldAssetPipelineError("asset_pipeline.world_id is required")
    world_id = world_id.lower()
    world_id = re.sub(r"[^a-z0-9_\-]", "-", world_id)
    world_id = re.sub(r"-{2,}", "-", world_id)
    world_id = world_id.strip("-")
    if not _WORLD_ID_PATTERN.fullmatch(world_id):
        raise WorldAssetPipelineError(
            f"Invalid world_id '{world_id}'. Expected pattern {_WORLD_ID_PATTERN.pattern}"
        )
    return world_id


def _resolve_type_folder(asset_type: Optional[str]) -> Tuple[str, str]:
    atype = (asset_type or "portrait").lower().strip()
    if atype not in _TYPE_FOLDERS:
        raise WorldAssetPipelineError(
            f"asset_pipeline.type must be one of {sorted(_TYPE_FOLDERS)}; got {asset_type!r}"
        )
    return atype, _TYPE_FOLDERS[atype]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _probe_image_dimensions(path: Path) -> Tuple[Optional[int], Optional[int]]:
    if Image is None:
        return None, None
    try:
        with Image.open(path) as img:  # type: ignore[attr-defined]
            return img.size  # type: ignore[return-value]
    except Exception:  # pragma: no cover - best effort
        return None, None


def _make_sidecar_payload(
    *,
    asset_id: str,
    asset_type: str,
    world_id: str,
    dest_rel: str,
    sidecar_rel: str,
    hash_value: str,
    bytes_size: int,
    width: Optional[int],
    height: Optional[int],
    pipeline_meta: Dict[str, Any],
    prompt_id: str,
    workflow_hash: Optional[str],
    workflow_label: Optional[str],
    entry: Dict[str, Any],
    request_meta: Dict[str, Any],
) -> Dict[str, Any]:
    license_meta = pipeline_meta.get("license") or {
        "id": "CC0-1.0",
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
    }
    if "id" not in license_meta:
        license_meta["id"] = "CC0-1.0"
    source_meta = pipeline_meta.get("source") or {
        "name": "ComfyUI workflow",
        "url": "",
    }
    tags = list(pipeline_meta.get("tags") or [])
    # allow request metadata to append hints without mutating originals
    request_tags = request_meta.get("tags")
    if isinstance(request_tags, (list, tuple)):
        tags.extend(str(tag) for tag in request_tags)
    workflow_payload = dict(pipeline_meta.get("workflow") or {})
    workflow_payload.setdefault("engine", "ComfyUI")
    if prompt_id:
        workflow_payload["prompt_id"] = prompt_id
    if workflow_hash:
        workflow_payload["workflow_hash"] = workflow_hash
    if workflow_label:
        workflow_payload.setdefault("workflow_label", workflow_label)
    if entry.get("node_id"):
        workflow_payload.setdefault("node_id", entry.get("node_id"))
    if entry.get("type"):
        workflow_payload.setdefault("output_type", entry.get("type"))
    if request_meta.get("context"):
        workflow_payload.setdefault("context", request_meta.get("context"))
    if request_meta.get("metadata"):
        workflow_payload.setdefault("metadata", request_meta.get("metadata"))

    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    payload: Dict[str, Any] = {
        "id": asset_id,
        "type": asset_type,
        "world_id": world_id,
        "path": dest_rel,
        "sidecar": sidecar_rel,
        "hash": f"sha256:{hash_value}",
        "license": license_meta,
        "source": source_meta,
        "tags": sorted(set(tag for tag in tags if tag)),
        "width": width,
        "height": height,
        "attribution": pipeline_meta.get("attribution"),
        "workflow": workflow_payload,
        "created_at": timestamp,
        "bytes": bytes_size,
    }
    extras = pipeline_meta.get("extras")
    if extras:
        payload["extras"] = extras
    return payload


def _update_manifest(
    *,
    world_id: str,
    asset_type: str,
    slug: str,
    path_rel: str,
    sidecar_rel: str,
    hash_value: str,
    tags: Iterable[str],
    width: Optional[int],
    height: Optional[int],
) -> str:
    manifest_dir = EXPORTS_ROOT / world_id / "meta"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / MANIFEST_NAME
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        existing = {}

    existing["world_id"] = world_id
    existing["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    assets = existing.setdefault("assets", {})
    type_bucket = assets.setdefault(asset_type, {})
    type_bucket[slug] = {
        "id": slug,
        "path": path_rel,
        "sidecar": sidecar_rel,
        "hash": f"sha256:{hash_value}",
        "tags": sorted(set(tag for tag in tags if tag)),
        "width": width,
        "height": height,
        "updated_at": existing["updated_at"],
    }

    manifest_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path.relative_to(ROOT).as_posix()


def save_world_asset(
    temp_path: Path,
    *,
    pipeline_meta: Dict[str, Any],
    entry: Dict[str, Any],
    prompt_id: str,
    workflow_hash: Optional[str],
    workflow_label: Optional[str],
    request_meta: Dict[str, Any],
) -> Dict[str, Any]:
    world_id = _ensure_world_id(pipeline_meta.get("world_id"))
    asset_type, type_folder = _resolve_type_folder(pipeline_meta.get("type"))
    slug_base = _ensure_slug(
        pipeline_meta.get("slug"),
        fallback=f"{asset_type}-{int(datetime.datetime.utcnow().timestamp())}",
    )
    overwrite = bool(pipeline_meta.get("overwrite"))

    suffix = temp_path.suffix or ""
    if not suffix:
        filename = entry.get("filename") or ""
        suffix = Path(filename).suffix or ".png"
    if suffix.lower() == ".tmp":
        suffix = ".png"

    dest_dir = EXPORTS_ROOT / world_id / type_folder
    dest_dir.mkdir(parents=True, exist_ok=True)

    slug = slug_base
    dest_path = dest_dir / f"{slug}{suffix}"
    if dest_path.exists() and not overwrite:
        counter = 2
        while dest_path.exists():
            slug = f"{slug_base}-v{counter}"
            dest_path = dest_dir / f"{slug}{suffix}"
            counter += 1

    shutil.copy2(temp_path, dest_path)
    bytes_size = dest_path.stat().st_size
    hash_value = _sha256(dest_path)
    width = entry.get("width")
    height = entry.get("height")
    if width is None or height is None:
        width_probe, height_probe = _probe_image_dimensions(dest_path)
        width = width or width_probe
        height = height or height_probe

    sidecar_path = dest_path.with_suffix(".json")
    dest_rel = dest_path.relative_to(ROOT).as_posix()
    sidecar_rel = sidecar_path.relative_to(ROOT).as_posix()

    sidecar_payload = _make_sidecar_payload(
        asset_id=slug,
        asset_type=asset_type,
        world_id=world_id,
        dest_rel=dest_rel,
        sidecar_rel=sidecar_rel,
        hash_value=hash_value,
        bytes_size=bytes_size,
        width=width,
        height=height,
        pipeline_meta=pipeline_meta,
        prompt_id=prompt_id,
        workflow_hash=workflow_hash,
        workflow_label=workflow_label,
        entry=entry,
        request_meta=request_meta,
    )

    sidecar_path.write_text(
        json.dumps(sidecar_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_rel = _update_manifest(
        world_id=world_id,
        asset_type=asset_type,
        slug=slug,
        path_rel=dest_rel,
        sidecar_rel=sidecar_rel,
        hash_value=hash_value,
        tags=sidecar_payload.get("tags", []),
        width=sidecar_payload.get("width"),
        height=sidecar_payload.get("height"),
    )

    LOGGER.info(
        "World asset saved world=%s type=%s slug=%s path=%s",
        world_id,
        asset_type,
        slug,
        dest_rel,
    )
    return {
        "id": slug,
        "world_id": world_id,
        "type": asset_type,
        "path": dest_rel,
        "sidecar": sidecar_rel,
        "hash": f"sha256:{hash_value}",
        "bytes": bytes_size,
        "width": sidecar_payload.get("width"),
        "height": sidecar_payload.get("height"),
        "manifest": manifest_rel,
        "sidecar_payload": sidecar_payload,
    }
