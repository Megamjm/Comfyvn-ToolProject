"""Utility helpers for moving files into the ComfyVN trash directory."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

TRASH_ROOT = Path("data/.trash")
TRASH_ROOT.mkdir(parents=True, exist_ok=True)


def move_to_trash(path: Path) -> Path:
    """Move *path* into the trash directory and return the new location."""
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return resolved

    relative = resolved.as_posix().lstrip("/").replace(":", "_")
    destination = TRASH_ROOT / f"{int(time.time())}_{relative.replace('/', '_')}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(resolved), str(destination))
    return destination


def list_trash(limit: int = 200) -> List[Dict[str, Any]]:
    """Return recent trash entries sorted by modification time."""
    items: List[Dict[str, Any]] = []
    for entry in sorted(TRASH_ROOT.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            items.append(
                {
                    "name": entry.name,
                    "size": entry.stat().st_size,
                    "modified": entry.stat().st_mtime,
                }
            )
            if len(items) >= limit:
                break
        except Exception:  # pragma: no cover - filesystem race
            continue
    return items


def restore(name: str) -> bool:
    """Restore the specified trash entry into ``data/recovered``."""
    source = (TRASH_ROOT / name).resolve()
    if not source.exists():
        return False

    destination = Path("data/recovered") / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return True


def purge(name: str) -> bool:
    """Delete the specified trash entry permanently."""
    target = (TRASH_ROOT / name).resolve()
    if not target.exists():
        return False

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except Exception:
        return False
    return True


__all__ = [
    "move_to_trash",
    "list_trash",
    "restore",
    "purge",
]
