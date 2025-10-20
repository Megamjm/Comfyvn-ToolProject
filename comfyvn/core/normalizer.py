"""Utilities for producing a ``comfyvn-pack`` from raw VN assets."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

LOGGER = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga"}
AUDIO_EXTS = {".ogg", ".wav", ".mp3", ".flac", ".m4a", ".aac"}
TEXT_EXTS = {".txt", ".ks", ".rpy", ".rpyc", ".json", ".csv", ".ybn", ".ss", ".org"}


def _stable_id(path: Path) -> str:
    digest = hashlib.sha1(path.as_posix().encode("utf-8"), usedforsecurity=False).hexdigest()
    return digest[:16]


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


@dataclass
class NormalizerResult:
    pack_root: Path
    manifest: Dict[str, object]
    warnings: List[str]


def normalize_tree(
    src_root: Path | str,
    out_dir: Path | str,
    *,
    engine: str,
    manifest_patch: Optional[Dict[str, object]] = None,
    hooks: Optional[Dict[str, str]] = None,
    include_dirs: Optional[Iterable[str]] = None,
) -> Path:
    """Copy assets from ``src_root`` into a comfyvn-pack structure."""

    src_path = Path(src_root).resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"source path does not exist: {src_path}")

    dest_root = Path(out_dir).resolve()
    pack_root = dest_root / "comfyvn_pack"
    raw_root = pack_root / "raw"
    assets_root = pack_root / "assets"

    for directory in [pack_root, raw_root, assets_root]:
        directory.mkdir(parents=True, exist_ok=True)

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

        # copy to raw mirror
        raw_dest = raw_root / rel_path
        raw_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, raw_dest)
        manifest["raw"].append({"path": str(rel_path)})

        category, subcategory = _categorize(rel_path)
        dest_rel: Path
        if category == "audio" and subcategory:
            dest_rel = Path("assets") / "audio" / subcategory / ( _stable_id(rel_path) + file_path.suffix.lower())
            dest_dir = assets_root / "audio" / subcategory
            dest_dir.mkdir(parents=True, exist_ok=True)
        elif category in {"bg", "cg", "sprites", "ui", "images"}:
            dest_rel = Path("assets") / category / ( _stable_id(rel_path) + file_path.suffix.lower())
            (assets_root / category).mkdir(parents=True, exist_ok=True)
        elif category == "text":
            dest_rel = Path("text") / rel_path
            (pack_root / "text" / rel_path.parent).mkdir(parents=True, exist_ok=True)
        else:
            # raw-only; nothing extra
            continue

        dest_abs = pack_root / dest_rel
        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest_abs)

        entry = {
            "id": _stable_id(rel_path),
            "path": dest_rel.as_posix(),
            "original": rel_path.as_posix(),
        }

        if category == "audio" and subcategory:
            manifest["assets"]["audio"][subcategory].append(entry)
        elif category in {"bg", "cg", "sprites", "ui", "images"}:
            manifest["assets"][category].append(entry)
        elif category == "text":
            manifest["text"].append(entry)

    manifest_path = pack_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    if warnings:
        LOGGER.warning("Normalizer warnings: \n%s", "\n".join(warnings))

    return pack_root


__all__ = ["normalize_tree", "NormalizerResult"]
