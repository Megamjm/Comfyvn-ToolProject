from __future__ import annotations

import json
# comfyvn/core/gpu_profiles.py
from dataclasses import asdict, dataclass
from pathlib import Path

import requests
from PySide6.QtGui import QAction

STORE = Path("comfyvn/data/gpu_profiles.json")
STORE.parent.mkdir(parents=True, exist_ok=True)
if not STORE.exists():
    STORE.write_text("[]", encoding="utf-8")


@dataclass
class GPUProfile:
    name: str
    kind: str  # "local" | "remote"
    endpoint: str
    notes: str = ""


def list_profiles() -> list[GPUProfile]:
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
        return [GPUProfile(**x) for x in data]
    except Exception:
        return []


def save_profiles(items: list[GPUProfile]):
    STORE.write_text(json.dumps([asdict(x) for x in items], indent=2), encoding="utf-8")


def add_profile(p: GPUProfile):
    items = list_profiles()
    items.append(p)
    save_profiles(items)


def health_ping(url: str, timeout=1.5) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False
