"""Utilities for producing a ``comfyvn-pack`` from raw VN assets.

The normalizer mirrors source assets under ``comfyvn_pack/raw`` for provenance,
derives deterministic asset identifiers, emits lightweight thumbnail
placeholders, and writes JSON sidecars for large binaries so downstream tools
have predictable metadata to inspect.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

LOGGER = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga"}
AUDIO_EXTS = {".ogg", ".wav", ".mp3", ".flac", ".m4a", ".aac"}
TEXT_EXTS = {".txt", ".ks", ".rpy", ".rpyc", ".json", ".csv", ".ybn", ".ss", ".org"}

THUMB_PLACEHOLDER_TEXT = "Placeholder thumbnail; generate via assets pipeline."
LARGE_BINARY_THRESHOLD = 8 * 1024 * 1024  # 8 MiB


def _stable_id(path: Path) -> str:
    digest = hashlib.sha1(
        path.as_posix().encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    return digest[:16]


def _sha1_file(path: Path) -> str:
    sha = hashlib.sha1(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _categorize(rel_path: Path) -> tuple[str, Optional[str]]:
    lower = rel_path.as_posix().lower()
    ext = rel_path.suffix.lower()
    parts = [p.lower() for p in rel_path.parts]

    if ext in IMAGE_EXTS:
        if any("bg" in part for part in parts):
            return ("bg", None)
        if any(part in {"cg", "event"} for part in parts):
            return ("cg", None)
        if any(part in {"sprite", "sprites", "chara", "character"} for part in parts):
            return ("sprites", None)
        if any(part in {"ui", "interface", "system"} for part in parts):
            return ("ui", None)
        return ("images", None)

    if ext in AUDIO_EXTS:
        if any(part in {"bgm", "music"} for part in parts):
            return ("audio", "bgm")
        if any(part in {"voice", "vo"} for part in parts):
            return ("audio", "voice")
        if any(part in {"se", "sfx", "sound"} for part in parts):
            return ("audio", "se")
        return ("audio", "other")

    if ext in TEXT_EXTS:
        return ("text", None)

    return ("raw", None)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass
class NormalizerResult:
    pack_root: Path
    manifest_path: Path
    manifest: Dict[str, object]
    warnings: List[str] = field(default_factory=list)
    thumbnails: List[str] = field(default_factory=list)
    sidecars: List[str] = field(default_factory=list)

    @property
    def output_dir(self) -> Path:
        return self.pack_root

    def joinpath(self, *parts: str | Path) -> Path:
        return self.pack_root.joinpath(*parts)

    def __truediv__(self, other: str | Path) -> Path:
        return self.pack_root / other

    def __fspath__(self) -> str:
        return self.pack_root.__fspath__()

    def __str__(self) -> str:
        return str(self.pack_root)


def normalize_tree(
    src_root: Path | str,
    out_dir: Path | str,
    *,
    engine: str,
    manifest_patch: Optional[Dict[str, object]] = None,
    hooks: Optional[Dict[str, str]] = None,
    include_dirs: Optional[Iterable[str]] = None,
) -> NormalizerResult:
    """Copy assets from ``src_root`` into a comfyvn-pack structure."""

    src_path = Path(src_root).resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"source path does not exist: {src_path}")

    dest_root = Path(out_dir).resolve()
    pack_root = dest_root / "comfyvn_pack"
    raw_root = pack_root / "raw"
    assets_root = pack_root / "assets"
    text_root = pack_root / "text"
    thumbs_root = pack_root / "thumbnails"
    meta_root = pack_root / "_meta"

    for directory in (
        pack_root,
        raw_root,
        assets_root,
        text_root,
        thumbs_root,
        meta_root,
    ):
        _ensure_dir(directory)

    manifest: Dict[str, object] = {
        "schema": "comfyvn-pack@1",
        "engine": engine,
        "sources": {"root": str(src_path)},
        "hooks": hooks or {},
        "assets": {
            "bg": [],
            "cg": [],
            "sprites": [],
            "ui": [],
            "images": [],
            "audio": {"bgm": [], "se": [], "voice": [], "other": []},
        },
        "text": [],
        "raw": [],
        "notes": [],
    }

    if manifest_patch:
        manifest.update(manifest_patch)

    include_set = {Path(d).as_posix().split("/")[0] for d in (include_dirs or [])}
    warnings: List[str] = []
    thumbnails: List[str] = []
    sidecars: List[str] = []

    for file_path in sorted(src_path.rglob("*")):
        if not file_path.is_file():
            continue
        try:
            rel_path = file_path.relative_to(src_path)
        except ValueError:
            continue
        if include_set and rel_path.parts[0] not in include_set:
            continue
        if "comfyvn_pack" in rel_path.parts:
            continue

        size = file_path.stat().st_size
        checksum = _sha1_file(file_path)
        stable_id = _stable_id(rel_path)

        raw_dest = raw_root / rel_path
        raw_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, raw_dest)
        manifest["raw"].append({"path": str(rel_path), "size": size, "hash": checksum})

        category, subcategory = _categorize(rel_path)
        dest_rel: Optional[Path] = None

        if category == "audio" and subcategory:
            dest_rel = (
                Path("assets")
                / "audio"
                / subcategory
                / (stable_id + file_path.suffix.lower())
            )
            _ensure_dir(assets_root / "audio" / subcategory)
        elif category in {"bg", "cg", "sprites", "ui", "images"}:
            dest_rel = (
                Path("assets") / category / (stable_id + file_path.suffix.lower())
            )
            _ensure_dir(assets_root / category)
        elif category == "text":
            dest_rel = Path("text") / rel_path
            _ensure_dir(text_root / rel_path.parent)
        else:
            # Non-normalised raw asset; capture via sidecar metadata only.
            if size >= LARGE_BINARY_THRESHOLD:
                sidecar_rel = Path("_meta") / f"{stable_id}.json"
                sidecar_abs = meta_root / f"{stable_id}.json"
                _write_json(
                    sidecar_abs,
                    {
                        "id": stable_id,
                        "original": rel_path.as_posix(),
                        "size": size,
                        "hash": checksum,
                        "note": "Large binary stored under comfyvn_pack/raw.",
                    },
                )
                sidecars.append(sidecar_rel.as_posix())
            continue

        dest_abs = pack_root / dest_rel
        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest_abs)

        entry = {
            "id": stable_id,
            "path": dest_rel.as_posix(),
            "original": rel_path.as_posix(),
            "size": size,
            "hash": checksum,
            "provenance": {
                "source": rel_path.as_posix(),
                "copied_from": str(file_path),
            },
        }

        if category == "audio" and subcategory:
            manifest["assets"]["audio"][subcategory].append(entry)
        elif category in {"bg", "cg", "sprites", "ui", "images"}:
            thumb_rel = Path("thumbnails") / f"{stable_id}.txt"
            thumb_abs = thumbs_root / f"{stable_id}.txt"
            if not thumb_abs.exists():
                thumb_abs.write_text(THUMB_PLACEHOLDER_TEXT, encoding="utf-8")
            entry["thumbnail"] = thumb_rel.as_posix()
            thumbnails.append(thumb_rel.as_posix())
            manifest["assets"][category].append(entry)
        elif category == "text":
            manifest["text"].append(entry)

        if size >= LARGE_BINARY_THRESHOLD and category != "raw":
            sidecar_rel = Path("_meta") / f"{stable_id}.json"
            sidecar_abs = meta_root / f"{stable_id}.json"
            _write_json(
                sidecar_abs,
                {
                    "id": stable_id,
                    "original": rel_path.as_posix(),
                    "normalised": dest_rel.as_posix(),
                    "size": size,
                    "hash": checksum,
                },
            )
            entry["sidecar"] = sidecar_rel.as_posix()
            sidecars.append(sidecar_rel.as_posix())

    manifest_path = pack_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if warnings:
        LOGGER.warning("Normalizer warnings:\n%s", "\n".join(warnings))

    return NormalizerResult(
        pack_root=pack_root,
        manifest_path=manifest_path,
        manifest=manifest,
        warnings=warnings,
        thumbnails=thumbnails,
        sidecars=sidecars,
    )


__all__ = ["normalize_tree", "NormalizerResult"]
