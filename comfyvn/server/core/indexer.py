from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtGui import QAction

INDEX_PATH = Path("./data/index.json")
SUPPORTED = {"scene", "character", "asset", "workflow", "artifact"}


def _now() -> float:
    return time.time()


def _file_text(p: Path) -> str:
    try:
        if p.suffix.lower() == ".json":
            return p.read_text(encoding="utf-8", errors="replace")
        if p.suffix.lower() in {".txt", ".md", ".csv", ".yml", ".yaml"}:
            return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return ""


def _sha256(p: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _load() -> Dict[str, Any]:
    if INDEX_PATH.exists():
        try:
            return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"items": [], "t": 0}
    return {"items": [], "t": 0}


def _save(db: Dict[str, Any]):
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(db, indent=2), encoding="utf-8")


def _sidecar_for_asset(p: Path) -> Path:
    return p.with_suffix(p.suffix + ".meta.json")


def _tags_from_json(data: Dict[str, Any]) -> List[str]:
    t = data.get("tags")
    if isinstance(t, list):
        return [str(x) for x in t]
    return []


def _collect() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    # scenes
    for p in Path("./data/scenes").glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            data = {}
        items.append(
            {
                "type": "scene",
                "key": p.stem,
                "path": p.as_posix(),
                "tags": _tags_from_json(data),
                "text": _file_text(p),
                "size": p.stat().st_size,
                "updated": p.stat().st_mtime,
            }
        )
    # characters
    for p in Path("./data/characters").glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            data = {}
        items.append(
            {
                "type": "character",
                "key": p.stem,
                "path": p.as_posix(),
                "tags": _tags_from_json(data),
                "text": _file_text(p),
                "size": p.stat().st_size,
                "updated": p.stat().st_mtime,
            }
        )
    # workflows
    for p in Path("./data/workflows").glob("*.json"):
        items.append(
            {
                "type": "workflow",
                "key": p.stem,
                "path": p.as_posix(),
                "tags": [],
                "text": _file_text(p),
                "size": p.stat().st_size,
                "updated": p.stat().st_mtime,
            }
        )
    # assets
    ad = Path("./data/assets")
    if ad.exists():
        for p in ad.rglob("*"):
            if p.is_dir() or "_thumbs" in p.parts:
                continue
            side = _sidecar_for_asset(p)
            tags: List[str] = []
            if side.exists():
                try:
                    tags = _tags_from_json(
                        json.loads(side.read_text(encoding="utf-8", errors="replace"))
                    )
                except Exception:
                    tags = []
            sha = _sha256(p)
            items.append(
                {
                    "type": "asset",
                    "key": str(p.relative_to(ad)),
                    "path": p.as_posix(),
                    "tags": tags,
                    "text": "",
                    "size": p.stat().st_size,
                    "updated": p.stat().st_mtime,
                    "sha256": sha,
                }
            )
    # artifacts (renders)
    rd = Path("./exports/renders")
    if rd.exists():
        for p in rd.rglob("*.png"):
            if "_thumbs" in p.parts:
                continue
            items.append(
                {
                    "type": "artifact",
                    "key": str(p.relative_to(rd)),
                    "path": p.as_posix(),
                    "tags": [],
                    "text": "",
                    "size": p.stat().st_size,
                    "updated": p.stat().st_mtime,
                }
            )
    return items


def reindex() -> Dict[str, Any]:
    items = _collect()
    # duplicate sets by sha256 for assets
    dup: Dict[str, List[str]] = {}
    for it in items:
        if it["type"] == "asset" and it.get("sha256"):
            dup.setdefault(it["sha256"], []).append(it["path"])
    duplicates = [{"sha256": k, "paths": v} for k, v in dup.items() if len(v) > 1]
    db = {"items": items, "duplicates": duplicates, "t": _now()}
    _save(db)
    return db


def ensure() -> Dict[str, Any]:
    if not INDEX_PATH.exists():
        return reindex()
    try:
        return _load()
    except Exception:
        return reindex()


def _score(q: str, it: Dict[str, Any]) -> float:
    ql = q.lower().strip()
    if not ql:
        return 0.1
    s = (
        it.get("key", "")
        + " "
        + it.get("path", "")
        + " "
        + " ".join(it.get("tags", []))
        + " "
        + (it.get("text", "")[:10000])
    ).lower()
    hit = s.count(ql)
    if hit:
        return min(10.0, 1.0 + hit * 0.5)
    # partials
    if ql in s:
        return 0.8
    return 0.0


def query(
    q: str = "",
    types: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    db = ensure()
    items = db.get("items", [])
    if types:
        types = [t for t in types if t in SUPPORTED]
        items = [it for it in items if it["type"] in types]
    if tags:
        st = set(tags)
        items = [it for it in items if st.issubset(set(it.get("tags", [])))]
    # score and sort
    scored = []
    for it in items:
        sc = _score(q, it)
        if sc > 0 or not q:
            scored.append((sc, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = [dict(it, score=float(sc)) for sc, it in scored[offset : offset + limit]]
    return {"ok": True, "total": len(scored), "items": out, "t": db.get("t")}


def duplicates() -> List[Dict[str, Any]]:
    db = ensure()
    return db.get("duplicates", [])


def tag_item(
    kind: str,
    key: str,
    add: Optional[List[str]] = None,
    remove: Optional[List[str]] = None,
) -> Dict[str, Any]:
    add = add or []
    remove = remove or []
    if kind not in SUPPORTED:
        return {"ok": False, "error": "unsupported"}
    if kind in {"scene", "character"}:
        base = Path(f"./data/{kind}s")
        p = (base / f"{key}.json").resolve()
        if not p.exists():
            return {"ok": False, "error": "not_found"}
        import json as _json

        data = _json.loads(p.read_text(encoding="utf-8", errors="replace"))
        tags = set([str(x) for x in (data.get("tags") or [])])
        for t in add:
            tags.add(str(t))
        for t in remove:
            tags.discard(str(t))
        data["tags"] = sorted(tags)
        p.write_text(_json.dumps(data, indent=2), encoding="utf-8")
        reindex()
        return {"ok": True, "tags": data["tags"]}
    if kind == "asset":
        base = Path("./data/assets")
        p = (base / key).resolve()
        if not p.exists():
            return {"ok": False, "error": "not_found"}
        side = p.with_suffix(p.suffix + ".meta.json")
        try:
            data = (
                json.loads(side.read_text(encoding="utf-8", errors="replace"))
                if side.exists()
                else {}
            )
        except Exception:
            data = {}
        tags = set([str(x) for x in (data.get("tags") or [])])
        for t in add:
            tags.add(str(t))
        for t in remove:
            tags.discard(str(t))
        data["tags"] = sorted(tags)
        side.write_text(json.dumps(data, indent=2), encoding="utf-8")
        reindex()
        return {"ok": True, "tags": data["tags"]}
    # workflow, artifact: maintain central tag db
    meta = Path("./data/metadata.json")
    try:
        db = (
            json.loads(meta.read_text(encoding="utf-8", errors="replace"))
            if meta.exists()
            else {}
        )
    except Exception:
        db = {}
    tags = set([str(x) for x in (db.get(kind, {}).get(key, {}).get("tags") or [])])
    for t in add:
        tags.add(str(t))
    for t in remove:
        tags.discard(str(t))
    db.setdefault(kind, {}).setdefault(key, {})["tags"] = sorted(tags)
    meta.write_text(json.dumps(db, indent=2), encoding="utf-8")
    reindex()
    return {"ok": True, "tags": sorted(tags)}
