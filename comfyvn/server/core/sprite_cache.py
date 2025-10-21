from __future__ import annotations
from PySide6.QtGui import QAction
from pathlib import Path
import json, hashlib
from comfyvn.config.runtime_paths import cache_dir

CACHE_DIR = cache_dir("sprites"); CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _key(d: dict) -> str:
    j = json.dumps(d, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(j.encode("utf-8")).hexdigest()[:16]

def lookup(char: str, mood: str, style: str | None = None) -> dict | None:
    k = _key({"char": char, "mood": mood, "style": style})
    f = CACHE_DIR / f"{k}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return None

def store(char: str, mood: str, style: str | None, path: str) -> dict:
    rec = {"char": char, "mood": mood, "style": style, "path": path}
    k = _key(rec); f = CACHE_DIR / f"{k}.json"
    f.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec
