"""
Asset registry rebuild helpers for ComfyVN.

This module provides a CLI entry point that scans the assets directory,
re-hashes every file, refreshes the SQLite registry rows, regenerates
metadata sidecars, and queues thumbnail/waveform previews.  The default
mode operates in-place without copying files, making it safe to run
multiple times as assets evolve.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from comfyvn.core.db_manager import DEFAULT_DB_PATH
from comfyvn.db import schema_v06
from comfyvn.studio.core import AssetRegistry
from comfyvn.config.runtime_paths import thumb_cache_dir

LOGGER = logging.getLogger("comfyvn.registry.rebuild")

SIDECAR_SUFFIX = ".asset.json"
LEGACY_SUFFIX = ".json"
META_DIR_NAME = "_meta"


@dataclass(frozen=True)
class RebuildSummary:
    """Simple summary of a registry rebuild operation."""

    processed: int
    skipped: int
    removed: int
    assets_root: Path
    thumb_root: Path

    def as_dict(self) -> Dict[str, int]:
        return {
            "processed": self.processed,
            "skipped": self.skipped,
            "removed": self.removed,
        }


def _prepare_thumb_root(thumbs_root: Optional[Path]) -> Path:
    """
    Resolve and prepare a thumbnail directory, falling back to the runtime cache.
    """

    candidates: List[Path] = []
    if thumbs_root is not None:
        candidates.append(thumbs_root.expanduser().resolve())
    repo_candidate = (Path("cache") / "thumbs").expanduser()
    candidates.append(repo_candidate)
    runtime_candidate = thumb_cache_dir().expanduser()
    candidates.append(runtime_candidate)

    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError as exc:
            LOGGER.debug("Unable to use thumbnail cache %s: %s", candidate, exc)
    # Final attempt: raise a descriptive error instead of silently failing.
    raise RuntimeError("Failed to prepare any thumbnail cache directory.")


def _iter_asset_files(root: Path) -> Iterator[Tuple[Path, Path]]:
    """
    Yield asset files under ``root`` ignoring sidecars and internal metadata folders.
    """

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if META_DIR_NAME in rel.parts:
            continue
        if rel.name.endswith(SIDECAR_SUFFIX):
            continue
        if rel.name.endswith(LEGACY_SUFFIX) and rel.with_suffix("").name.endswith(".asset"):
            continue
        yield path, rel


def _derive_asset_type(rel_path: Path) -> str:
    """
    Guess the asset type based on its top-level folder or file suffix.
    """

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


def _load_sidecar_payload(base_path: Path) -> Tuple[Dict[str, object], Optional[str]]:
    """
    Load existing sidecar metadata if present.

    Returns a tuple of (meta_payload, license_tag).
    """

    candidates = (
        base_path.with_suffix(base_path.suffix + SIDECAR_SUFFIX),
        base_path.with_suffix(base_path.suffix + LEGACY_SUFFIX),
    )
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive parsing
            LOGGER.warning("Failed to parse sidecar %s: %s", candidate, exc)
            continue
        meta = data.get("meta")
        payload = dict(meta) if isinstance(meta, dict) else {}
        for key in ("origin", "tags", "seed", "workflow", "digest_sha256", "filesize_bytes"):
            if key in data and key not in payload:
                payload[key] = data[key]
        license_tag = data.get("license")
        return payload, license_tag if isinstance(license_tag, str) else None
    return {}, None


def _compute_digest(path: Path, chunk_size: int = 1 << 16) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _seed_from_digest(digest: str) -> int:
    """
    Derive a deterministic seed from the leading bytes of the SHA-256 digest.
    """

    return int(digest[:12], 16) & 0x7FFFFFFF


def _tags_from_path(rel_path: Path) -> List[str]:
    tags: List[str] = []
    parts = list(rel_path.parts)
    for part in parts[:-1]:
        if part and part != META_DIR_NAME:
            tags.append(part.lower())
    stem = rel_path.stem.lower()
    if stem:
        tags.append(stem)
    # Deduplicate while preserving order
    seen: set[str] = set()
    ordered: List[str] = []
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        ordered.append(tag)
    return ordered


def rebuild_from_disk(
    *,
    assets_root: Path,
    db_path: Path,
    thumbs_root: Optional[Path] = None,
    project_id: str = "default",
    remove_stale: bool = True,
    wait_for_thumbs: bool = True,
) -> RebuildSummary:
    """
    Rebuild the asset registry by scanning ``assets_root`` and updating the database.
    """

    if thumbs_root is None:
        resolved_thumbs = _prepare_thumb_root(None)
    else:
        resolved_thumbs = _prepare_thumb_root(thumbs_root)

    assets_root.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    meta_root = assets_root / META_DIR_NAME

    schema_v06.ensure_schema(db_path)
    registry = AssetRegistry(
        db_path=db_path,
        project_id=project_id,
        assets_root=assets_root,
        thumb_root=resolved_thumbs,
        meta_root=meta_root,
    )

    processed = 0
    skipped = 0
    for file_path, rel_path in _iter_asset_files(assets_root):
        asset_type = _derive_asset_type(rel_path)
        meta_payload, license_tag = _load_sidecar_payload(file_path)
        if "license" in meta_payload:
            existing_license = meta_payload.pop("license")
            if not license_tag and isinstance(existing_license, str):
                license_tag = existing_license
        meta_payload.pop("preview", None)
        meta_payload.setdefault("origin", "registry.rebuild.from_disk")
        meta_payload.setdefault("tags", _tags_from_path(rel_path))
        try:
            checksum = _compute_digest(file_path)
            size_bytes = file_path.stat().st_size
        except OSError as exc:
            skipped += 1
            LOGGER.error("Failed to stat %s: %s", file_path, exc)
            continue
        meta_payload["digest_sha256"] = checksum
        meta_payload["filesize_bytes"] = size_bytes
        meta_payload.setdefault("seed", _seed_from_digest(checksum))
        meta_payload.setdefault(
            "workflow",
            {"hash": checksum, "source": "rebuild", "path": rel_path.as_posix()},
        )
        try:
            registry.register_file(
                file_path,
                asset_type=asset_type,
                dest_relative=rel_path,
                metadata=meta_payload,
                copy=False,
                license_tag=license_tag or "unknown",
            )
            processed += 1
        except Exception as exc:  # pragma: no cover - defensive
            skipped += 1
            LOGGER.error("Failed to register %s: %s", file_path, exc)

    removed = 0
    if remove_stale:
        for asset in registry.list_assets():
            rel_path = Path(asset["path"])
            full_path = (registry.ASSETS_ROOT / rel_path).resolve()
            if not full_path.exists():
                LOGGER.warning("Removing stale asset %s (%s)", asset["uid"], full_path)
                registry.remove_asset(asset["uid"], delete_files=False)
                removed += 1

    if wait_for_thumbs:
        AssetRegistry.wait_for_thumbnails(timeout=30.0)

    return RebuildSummary(
        processed=processed,
        skipped=skipped,
        removed=removed,
        assets_root=assets_root,
        thumb_root=registry.THUMB_ROOT,
    )


def smoke_check(db_path: Path | str) -> Tuple[int, int]:
    """
    Run a lightweight smoke check ensuring scenes and assets have content.
    """

    path = Path(db_path).expanduser()
    with sqlite3.connect(path) as conn:
        assets_count = conn.execute("SELECT COUNT(*) FROM assets_registry").fetchone()[0]
        scenes_count = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
    LOGGER.info("Smoke check assets=%s scenes=%s", assets_count, scenes_count)
    return int(assets_count), int(scenes_count)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="comfyvn.registry.rebuild",
        description="Rebuild the ComfyVN asset registry from disk.",
    )
    parser.add_argument(
        "--from-disk",
        action="store_true",
        help="Scan the assets directory and re-register every asset.",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help="Assets root directory (defaults to autodetect).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--thumbs-dir",
        type=Path,
        default=None,
        help="Thumbnail cache directory (default: cache/thumbs).",
    )
    parser.add_argument(
        "--project-id",
        default="default",
        help="Project identifier (default: default).",
    )
    parser.add_argument(
        "--no-remove-stale",
        action="store_true",
        help="Skip removing registry rows for missing files.",
    )
    parser.add_argument(
        "--no-thumb-wait",
        action="store_true",
        help="Do not wait for thumbnail worker completion.",
    )
    parser.add_argument(
        "--no-smoke",
        action="store_true",
        help="Skip the post-rebuild smoke check.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-error logging output.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging for troubleshooting.",
    )
    return parser


def _autodetect_assets_root(candidate: Optional[Path]) -> Path:
    if candidate:
        return candidate.expanduser().resolve()
    for option in (Path("assets"), Path("data/assets"), Path("comfyvn/data/assets")):
        if option.exists():
            return option.expanduser().resolve()
    return Path("assets").expanduser().resolve()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    level = logging.DEBUG if args.verbose else logging.INFO
    if args.quiet:
        level = max(logging.ERROR, level)
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    if not args.from_disk:
        parser.print_help()
        return 1

    assets_root = _autodetect_assets_root(args.assets_dir)
    db_path = args.db_path.expanduser().resolve()

    LOGGER.info("Starting registry rebuild from %s (db=%s)", assets_root, db_path)
    summary = rebuild_from_disk(
        assets_root=assets_root,
        db_path=db_path,
        thumbs_root=args.thumbs_dir,
        project_id=args.project_id,
        remove_stale=not args.no_remove_stale,
        wait_for_thumbs=not args.no_thumb_wait,
    )
    LOGGER.info(
        "Rebuilt registry from %s (db=%s, thumbs=%s)",
        summary.assets_root,
        db_path,
        summary.thumb_root,
    )
    LOGGER.info(
        "Processed %(processed)s assets (%(skipped)s skipped, %(removed)s removed).",
        summary.as_dict(),
    )

    if not args.no_smoke:
        assets_count, scenes_count = smoke_check(db_path)
        if assets_count <= 0 or scenes_count <= 0:
            LOGGER.error(
                "Smoke check failed: assets=%s scenes=%s", assets_count, scenes_count
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
