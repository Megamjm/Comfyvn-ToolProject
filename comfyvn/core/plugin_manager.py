from __future__ import annotations

# comfyvn/core/plugin_manager.py
from pathlib import Path

from PySide6.QtGui import QAction


def get_plugins(kind: str = None):
    base_dirs = [Path("plugins"), Path("extensions")]
    results = []
    for b in base_dirs:
        if not b.exists():
            continue
        for f in b.glob("*.py"):
            if kind and kind not in f.stem:
                continue
            results.append(f.stem)
    return results
