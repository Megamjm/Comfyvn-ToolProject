import hashlib
import json
import shutil
import time
# comfyvn/server/core/assets.py
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtGui import QAction

ASSETS = Path("data/assets")
ASSETS.mkdir(parents=True, exist_ok=True)
CACHE = Path("data/cache")
CACHE.mkdir(parents=True, exist_ok=True)


def _hash_blob(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:32]


def put_bytes(
    b: bytes, *, kind: str = "generic", meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    h = _hash_blob(b)
    p = ASSETS / f"{kind}_{h}"
    p.write_bytes(b)
    (ASSETS / f"{p.name}.json").write_text(
        json.dumps(
            {"hash": h, "kind": kind, "ts": time.time(), "meta": meta or {}}, indent=2
        ),
        encoding="utf-8",
    )
    return {"ok": True, "key": p.name, "hash": h}


def link_cache(src_key: str, tag: str) -> Dict[str, Any]:
    src = ASSETS / src_key
    if not src.exists():
        return {"ok": False, "error": "missing"}
    dst = CACHE / f"{tag}_{src.name}"
    try:
        if dst.exists():
            dst.unlink()
        dst.hardlink_to(src)
    except Exception:
        shutil.copy2(src, dst)
    return {"ok": True, "cache_key": dst.name}


def stat(key: str) -> Dict[str, Any]:
    p = ASSETS / key
    if not p.exists():
        return {"ok": False, "error": "missing"}
    meta = {}
    jf = ASSETS / f"{p.name}.json"
    if jf.exists():
        meta = json.loads(jf.read_text(encoding="utf-8"))
    return {"ok": True, "size": p.stat().st_size, "meta": meta}
