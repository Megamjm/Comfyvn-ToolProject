#!/usr/bin/env python3
"""
Utility to rebuild the ComfyVN asset registry from the on-disk assets folder.

This scans the assets directory, re-registers every asset with the SQLite
registry, rewrites sidecars, and triggers thumbnail/waveform generation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfyvn.studio.core import AssetRegistry

LOGGER = logging.getLogger("rebuild_asset_registry")


def _load_sidecar(base_path: Path) -> Tuple[Dict[str, object], Optional[str]]:
    """Load existing sidecar metadata if present."""
    candidates = [
        base_path.with_suffix(base_path.suffix + ".asset.json"),
        base_path.with_suffix(base_path.suffix + ".json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
                license_tag = (
                    data.get("license")
                    if isinstance(data.get("license"), str)
                    else None
                )
                return dict(meta or {}), license_tag
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Failed to parse sidecar %s: %s", candidate, exc)
    return {}, None


def _derive_asset_type(rel_path: Path) -> str:
    if rel_path.parts and rel_path.parts[0] != rel_path.name:
        return rel_path.parts[0]
    suffix = rel_path.suffix.lower().lstrip(".")
    if suffix in {"png", "jpg", "jpeg", "webp", "bmp", "gif"}:
        return "images"
    if suffix in {"wav", "mp3", "ogg", "flac"}:
        return "audio"
    if suffix == "json":
        return "json"
    return "generic"


def _iter_asset_files(root: Path) -> Iterable[Tuple[Path, Path]]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if "_meta" in rel.parts:
            continue
        if rel.name.endswith(".asset.json"):
            continue
        if rel.name.endswith(".json") and rel.with_suffix("").name.endswith(".asset"):
            continue
        yield path, rel


def _compute_digest(path: Path, chunk_size: int = 1 << 16) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def rebuild_registry(
    *,
    assets_root: Path,
    db_path: Path,
    thumbs_root: Optional[Path] = None,
    project_id: str = "default",
) -> Dict[str, int]:
    if thumbs_root is None:
        thumbs_root = ROOT / "cache" / "thumbs"

    registry = AssetRegistry(
        db_path=db_path,
        project_id=project_id,
        assets_root=assets_root,
        thumb_root=thumbs_root,
    )

    processed = 0
    skipped = 0
    for file_path, rel_path in _iter_asset_files(assets_root):
        asset_type = _derive_asset_type(rel_path)
        meta_payload, license_tag = _load_sidecar(file_path)
        meta_payload.setdefault("origin", "rebuild_asset_registry")
        try:
            checksum = _compute_digest(file_path)
            size_bytes = file_path.stat().st_size
        except OSError as exc:
            skipped += 1
            LOGGER.error("Failed to stat %s: %s", file_path, exc)
            continue
        meta_payload.setdefault("digest_sha256", checksum)
        meta_payload.setdefault("filesize_bytes", size_bytes)
        try:
            registry.register_file(
                file_path,
                asset_type=asset_type,
                dest_relative=rel_path,
                metadata=meta_payload,
                copy=False,
                license_tag=license_tag,
            )
            processed += 1
        except Exception as exc:  # pragma: no cover - defensive
            skipped += 1
            LOGGER.error("Failed to register %s: %s", file_path, exc)

    # Remove stale registry entries whose files disappeared.
    removed = 0
    for asset in registry.list_assets():
        rel_path = Path(asset["path"])
        full_path = (registry.ASSETS_ROOT / rel_path).resolve()
        if not full_path.exists():
            LOGGER.warning("Removing stale asset %s (%s)", asset["uid"], full_path)
            registry.remove_asset(asset["uid"], delete_files=False)
            removed += 1

    AssetRegistry.wait_for_thumbnails(timeout=30.0)
    return {"processed": processed, "skipped": skipped, "removed": removed}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild the ComfyVN asset registry from disk."
    )
    parser.add_argument(
        "--assets-dir",
        default="assets",
        help="Assets root directory (default: assets/)",
    )
    parser.add_argument(
        "--db-path",
        default="comfyvn/data/comfyvn.db",
        help="SQLite database path (default: comfyvn/data/comfyvn.db)",
    )
    parser.add_argument(
        "--thumbs-dir",
        default=None,
        help="Override thumbnail cache directory (default: auto-detected)",
    )
    parser.add_argument(
        "--project-id", default="default", help="Project identifier (default: default)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    assets_root = Path(args.assets_dir).expanduser().resolve()
    db_path = Path(args.db_path).expanduser().resolve()
    thumbs_root = (
        Path(args.thumbs_dir).expanduser().resolve()
        if args.thumbs_dir
        else (ROOT / "cache" / "thumbs")
    )

    assets_root.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    thumbs_root.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Rebuilding asset registry at %s (database=%s)", assets_root, db_path)
    summary = rebuild_registry(
        assets_root=assets_root,
        db_path=db_path,
        thumbs_root=thumbs_root,
        project_id=args.project_id,
    )
    LOGGER.info(
        "Processed %(processed)s assets (%(skipped)s skipped, %(removed)s removed).",
        summary,
    )


if __name__ == "__main__":
    main()
