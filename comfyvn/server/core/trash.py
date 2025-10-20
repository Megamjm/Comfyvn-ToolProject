from __future__ import annotations
from PySide6.QtGui import QAction
import os, time, shutil
from pathlib import Path
from typing import List, Dict, Any

TRASH = Path("./data/.trash"); TRASH.mkdir(parents=True, exist_ok=True)

def move_to_trash(fp: Path) -> Path:
    fp = fp.resolve()
    if not fp.exists(): return fp
    rel = fp.as_posix().lstrip("/").replace(":", "_")
    dst = TRASH / f"{int(time.time())}_{rel.replace('/', '_')}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(fp.as_posix(), dst.as_posix())
    return dst

def list_trash(limit: int = 200) -> List[Dict[str, Any]]:
    items = []
    for p in sorted(TRASH.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            items.append({"name": p.name, "size": p.stat().st_size, "t": p.stat().st_mtime})
            if len(items) >= limit: break
        except Exception:
            pass
    return items

def restore(name: str) -> bool:
    p = (TRASH / name).resolve()
    if not p.exists(): return False
    # restore to data/recovered/<name>
    out = Path("./data/recovered") / name
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(p.as_posix(), out.as_posix())
    return True

def purge(name: str) -> bool:
    p = (TRASH / name).resolve()
    if not p.exists(): return False
    try:
        p.unlink()
    except IsADirectoryError:
        shutil.rmtree(p)
    except Exception:
        return False
    return True