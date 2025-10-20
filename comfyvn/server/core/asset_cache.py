from __future__ import annotations
from PySide6.QtGui import QAction

import json, hashlib
from pathlib import Path
from typing import Dict

ASSET_ROOT = Path("data/assets")
META = ASSET_ROOT / "meta.json"
ASSET_ROOT.mkdir(parents=True, exist_ok=True)
if not META.exists():
    META.write_text("{}", encoding="utf-8")

def _load() -> Dict:
    return json.loads(META.read_text(encoding="utf-8"))

def _save(d: Dict):
    META.write_text(json.dumps(d, indent=2), encoding="utf-8")

def put(kind: str, name: str, path: str) -> dict:
    d = _load()
    h = hashlib.sha1((kind+"|"+name+"|"+path).encode()).hexdigest()[:12]
    d.setdefault(kind, {})[name] = {"path": path, "id": h}
    _save(d)
    return {"ok": True, "id": h}

def list_all() -> dict:
    return _load()