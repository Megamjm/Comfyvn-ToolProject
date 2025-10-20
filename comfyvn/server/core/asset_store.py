from __future__ import annotations
from PySide6.QtGui import QAction
import os, time, hashlib
from pathlib import Path
from typing import List, Dict, Optional

S3_BUCKET = os.getenv("S3_BUCKET","").strip()
ASSETS_ROOT = Path("./data/assets")

def _hash_name(name: str) -> str:
    return hashlib.sha256(f"{time.time()}::{name}".encode()).hexdigest()[:40]

# Local FS backend
def put_bytes(data: bytes, *, filename: str) -> str:
    ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
    key = _hash_name(filename) + "_" + filename
    (ASSETS_ROOT / key).write_bytes(data)
    return key

def list_keys(prefix: str="") -> List[str]:
    ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
    ks=[]
    for p in ASSETS_ROOT.glob("**/*"):
        if p.is_file():
            rel = p.name
            if not prefix or rel.startswith(prefix):
                ks.append(rel)
    return sorted(ks)

def delete_keys(keys: List[str]) -> int:
    n=0
    for k in keys:
        p = ASSETS_ROOT / k
        if p.exists():
            try: p.unlink(); n+=1
            except Exception: pass
    return n

def get_url(key: str) -> str:
    # served via /asset-store/static/{key}
    return f"/asset-store/static/{key}"