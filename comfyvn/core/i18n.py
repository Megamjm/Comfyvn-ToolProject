import json
import re
from pathlib import Path, PurePosixPath

from PySide6.QtGui import QAction


def export_strings(scene: dict):
    out = []
    for ln in scene.get("lines", []):
        txt = (ln.get("text") or "").strip()
        if txt:
            out.append(txt)
    return {"count": len(out), "strings": out}


def translate_strings(strings: list, target: str = "en"):
    # placeholder: identity map with tag
    return [{"src": s, "tgt": f"[{target}] {s}"} for s in strings or []]


def pack_locale(scene_id: str, pairs: list, lang: str = "en"):
    base = Path("data/i18n") / scene_id
    base.mkdir(parents=True, exist_ok=True)
    fp = base / f"{lang}.json"
    fp.write_text(
        json.dumps({"lang": lang, "items": pairs}, indent=2), encoding="utf-8"
    )
    return str(fp)
