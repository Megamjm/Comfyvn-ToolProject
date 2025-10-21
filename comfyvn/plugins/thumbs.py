from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from PIL import Image
from PySide6.QtGui import QAction

from comfyvn.ext.plugins import Plugin

TH_DIR = Path("./data/assets/_thumbs")
TH_DIR.mkdir(parents=True, exist_ok=True)


def make_thumb(payload: Dict[str, Any], job_id: str | None):
    path = payload.get("path")
    size = int(payload.get("size") or 256)
    if not path:
        return {"ok": False, "error": "path required"}
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "not found"}
    out = TH_DIR / (p.stem + f"_{size}.jpg")
    try:
        with Image.open(p) as im:
            im.thumbnail((size, size))
            bg = Image.new("RGB", im.size, (0, 0, 0))
            bg.paste(im, (0, 0))
            bg.save(out, "JPEG", quality=85)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "thumb": out.as_posix()}


plugin = Plugin(
    name="thumbs",
    jobs={"make_thumb": make_thumb},
    meta={"builtin": True, "desc": "Generate thumbnails for local images"},
)
