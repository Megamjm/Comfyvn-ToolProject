from __future__ import annotations
from PySide6.QtGui import QAction
from pathlib import Path
import json

def scan(root: str) -> dict:
    r = Path(root)
    out = []
    if not r.exists():
        return {"ok": False, "error": "root not found"}
    for p in r.rglob("*"):
        if p.is_file():
            out.append({"path": str(p), "size": p.stat().st_size})
    idx = {"ok": True, "count": len(out), "items": out}
    Path("data/indexes").mkdir(parents=True, exist_ok=True)
    (Path("data/indexes") / "assets.json").write_text(json.dumps(idx, indent=2), encoding="utf-8")
    return idx