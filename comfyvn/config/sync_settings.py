from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from comfyvn.sync.cloud.manifest import (
    DEFAULT_EXCLUDE_PATTERNS,
    DEFAULT_INCLUDE_FOLDERS,
)

CONFIG_CANDIDATES: Sequence[Path] = (Path("config/comfyvn.json"), Path("comfyvn.json"))


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def load_sync_settings() -> Dict[str, Any]:
    settings: Dict[str, Any] = {
        "include": list(DEFAULT_INCLUDE_FOLDERS),
        "exclude": list(DEFAULT_EXCLUDE_PATTERNS),
        "snapshot_prefix": "snapshots",
        "default_root": ".",
    }
    for path in CONFIG_CANDIDATES:
        payload = _read_json(path)
        sync_section = payload.get("sync")
        if not isinstance(sync_section, dict):
            continue
        include = sync_section.get("include")
        exclude = sync_section.get("exclude")
        snapshot_prefix = sync_section.get("snapshot_prefix")
        default_root = sync_section.get("default_root")
        if isinstance(include, list):
            settings["include"] = [
                str(item) for item in include if isinstance(item, str)
            ]
        if isinstance(exclude, list):
            settings["exclude"] = [
                str(item) for item in exclude if isinstance(item, str)
            ]
        if isinstance(snapshot_prefix, str) and snapshot_prefix:
            settings["snapshot_prefix"] = snapshot_prefix
        if isinstance(default_root, str) and default_root:
            settings["default_root"] = default_root
    return settings


__all__ = ["load_sync_settings"]
