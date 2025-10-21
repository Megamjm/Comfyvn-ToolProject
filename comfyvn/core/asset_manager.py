from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from PySide6.QtGui import QAction

from comfyvn.core.provenance import stamp_path

# comfyvn/core/asset_manager.py


LOGGER = logging.getLogger("comfyvn.core.asset_manager")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSET_DB = PROJECT_ROOT / "comfyvn" / "data" / "assets.json"


def _relative_to_root(path: Path) -> str:
    try:
        rel = path.relative_to(PROJECT_ROOT)
    except ValueError:
        rel = Path(os.path.relpath(path, PROJECT_ROOT))
    return rel.as_posix()


def _normalise_entry(entry: str) -> str:
    candidate = Path(entry)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return _relative_to_root(candidate)


def _ensure_normalised(data: dict[str, list[str]]) -> bool:
    changed = False
    for kind, entries in list(data.items()):
        if not isinstance(entries, list):
            continue
        normalised: list[str] = []
        for entry in entries:
            if not isinstance(entry, str):
                continue
            rel = _normalise_entry(entry)
            if rel != entry:
                changed = True
            if rel not in normalised:
                normalised.append(rel)
        data[kind] = normalised
    return changed


def _write_assets(data: dict[str, list[str]]) -> None:
    ASSET_DB.parent.mkdir(parents=True, exist_ok=True)
    ASSET_DB.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_assets(kind=None):
    if ASSET_DB.exists():
        data = json.loads(ASSET_DB.read_text(encoding="utf-8"))
        if _ensure_normalised(data):
            _write_assets(data)
    else:
        data = {"images": [], "audio": [], "sprites": []}
    return data if kind is None else data.get(kind, [])


def register_asset(kind: str, path: str):
    data = list_assets()
    asset_path = Path(path)
    if not asset_path.is_absolute():
        asset_path = (PROJECT_ROOT / asset_path).resolve()
    else:
        asset_path = asset_path.resolve()
    rel = _relative_to_root(asset_path)
    entries = data.setdefault(kind, [])
    if rel not in entries:
        entries.append(rel)
    _write_assets(data)
    if asset_path.exists():
        stamp_path(
            asset_path,
            source="core.asset_manager.register",
            inputs={"kind": kind},
        )
    else:  # pragma: no cover - defensive
        LOGGER.warning("Skipped provenance stamp; asset path missing: %s", path)


def import_folder(folder: str, kind: str = "images"):
    p = Path(folder)
    for f in p.glob("*.*"):
        if f.suffix.lower() in [
            ".png",
            ".jpg",
            ".jpeg",
            ".wav",
            ".mp3",
            ".ogg",
            ".flac",
        ]:
            register_asset(kind, str(f.resolve()))
    return list_assets(kind)
