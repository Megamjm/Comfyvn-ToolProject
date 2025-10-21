from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtGui import QAction
from whoosh import index
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import DATETIME, ID, KEYWORD, NUMERIC, TEXT, Schema
from whoosh.qparser import MultifieldParser, OrGroup, QueryParser
from whoosh.query import And, Or, Term

DATA_DIR = Path("./data/search")
DATA_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DIR = DATA_DIR / "index"
MANIFEST = DATA_DIR / "manifest.json"
SAVED = DATA_DIR / "saved.json"

SCHEMA = Schema(
    doc_id=ID(stored=True, unique=True),
    dtype=KEYWORD(stored=True, lowercase=True, commas=True),
    title=TEXT(stored=True, analyzer=StemmingAnalyzer()),
    content=TEXT(analyzer=StemmingAnalyzer()),
    tags=KEYWORD(lowercase=True, commas=True, scorable=True, stored=True),
    project=ID(stored=True),
    updated=NUMERIC(stored=True, sortable=True),
)

SYN = {
    "dialog": ["dialogue", "conversation", "chat"],
    "scene": ["chapter", "episode"],
    "character": ["persona", "actor"],
    "import": ["ingest", "upload"],
}


def _hash(o: Any) -> str:
    return hashlib.sha256(
        json.dumps(o, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _load(
    db_url_env: str | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    # scenes, characters
    scenes, chars = [], []
    # Prefer DB when configured
    use_db = bool(os.getenv("DB_URL", "").strip())
    if use_db:
        try:
            from sqlalchemy.orm import Session

            from comfyvn.server.core.db import (CharacterRow, SceneRow, get_db,
                                                init_db)

            init_db()
            for db in get_db():
                rows = db.query(SceneRow).all()
                for r in rows:
                    try:
                        d = json.loads(r.data or "{}")
                        d["__updated"] = r.updated
                        scenes.append(d)
                    except Exception:
                        pass
                rows = db.query(CharacterRow).all()
                for r in rows:
                    try:
                        d = json.loads(r.data or "{}")
                        d["__updated"] = r.updated
                        chars.append(d)
                    except Exception:
                        pass
                break
        except Exception:
            use_db = False
    if not use_db:
        sdir = Path("./data/scenes")
        sdir.mkdir(parents=True, exist_ok=True)
        for p in sdir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                d["__updated"] = p.stat().st_mtime
                scenes.append(d)
            except Exception:
                pass
        cdir = Path("./data/characters")
        cdir.mkdir(parents=True, exist_ok=True)
        for p in cdir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                d["__updated"] = p.stat().st_mtime
                chars.append(d)
            except Exception:
                pass
    return scenes, chars


def _doc_from_scene(s: Dict[str, Any]) -> Dict[str, Any]:
    sid = s.get("scene_id") or s.get("id") or _hash(s)[:12]
    title = s.get("title") or sid
    lines = s.get("lines") or []
    content = "\n".join(str(x.get("text") or "") for x in lines)[:100000]
    tags = s.get("tags") or []
    project = s.get("project_id") or _project_from_tags(tags)
    return dict(
        doc_id=f"scene:{sid}",
        dtype="scene",
        title=title,
        content=content,
        tags=",".join(tags),
        project=str(project or ""),
        updated=int(s.get("__updated") or time.time()),
    )


def _doc_from_char(c: Dict[str, Any]) -> Dict[str, Any]:
    name = c.get("name") or c.get("id") or _hash(c)[:12]
    bio = c.get("bio") or c.get("desc") or ""
    tags = c.get("tags") or []
    project = c.get("project_id") or _project_from_tags(tags)
    return dict(
        doc_id=f"character:{name}",
        dtype="character",
        title=name,
        content=bio,
        tags=",".join(tags),
        project=str(project or ""),
        updated=int(c.get("__updated") or time.time()),
    )


def _project_from_tags(tags: List[str]) -> str | None:
    for t in tags or []:
        if t.startswith("project:"):
            return t.split(":", 1)[1]
    return None


def _open_or_create():
    if not INDEX_DIR.exists():
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
    if not index.exists_in(INDEX_DIR):
        return index.create_in(INDEX_DIR, SCHEMA)
    return index.open_dir(INDEX_DIR)


def _expand_synonyms(q: str) -> str:
    tokens = q.split()
    exp = []
    for tok in tokens:
        syns = SYN.get(tok.lower())
        if syns:
            exp.append("(" + " OR ".join([tok] + syns) + ")")
        else:
            exp.append(tok)
    return " ".join(exp)


def reindex(full: bool = False) -> Dict[str, Any]:
    scenes, chars = _load()
    docs = [_doc_from_scene(s) for s in scenes] + [_doc_from_char(c) for c in chars]
    man = {"docs": {}}
    if MANIFEST.exists():
        try:
            man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            man = {"docs": {}}
    ix = _open_or_create()
    w = ix.writer(limitmb=256, procs=1, multisegment=True)
    added = 0
    updated = 0
    seen_ids = set()
    for d in docs:
        did = d["doc_id"]
        seen_ids.add(did)
        h = _hash(d)
        if not full and man["docs"].get(did) == h:
            continue
        # delete + add (simpler than update in older Whoosh)
        try:
            w.delete_by_term("doc_id", did)
        except Exception:
            pass
        w.add_document(**d)
        man["docs"][did] = h
        added += 1
    w.commit()
    # remove stale docs from manifest; leave index cleanup to periodic full
    for k in list(man["docs"].keys()):
        if k not in seen_ids and full:
            del man["docs"][k]
    MANIFEST.write_text(json.dumps(man, indent=2), encoding="utf-8")
    return {"ok": True, "added_or_updated": added, "total": len(man["docs"])}


def facets(
    query: str = "", filters: Dict[str, Any] | None = None, limit: int = 100
) -> Dict[str, Any]:
    filters = filters or {}
    ix = _open_or_create()
    from collections import Counter

    f_type = Counter()
    f_tag = Counter()
    f_project = Counter()
    with ix.searcher() as s:
        qp = MultifieldParser(
            ["title", "content", "tags"], schema=ix.schema, group=OrGroup.factory(0.9)
        )
        qstr = _expand_synonyms(query or "")
        q = qp.parse(qstr) if qstr else qp.parse("*")
        res = s.search(q, limit=limit)
        for hit in res:
            f_type[hit["dtype"]] += 1
            for t in (hit.get("tags") or "").split(","):
                if t:
                    f_tag[t] += 1
            proj = hit.get("project") or ""
            if proj:
                f_project[proj] += 1
    return {
        "type": f_type.most_common(50),
        "tag": f_tag.most_common(50),
        "project": f_project.most_common(50),
    }


def search(body: Dict[str, Any]) -> Dict[str, Any]:
    q = str(body.get("q") or "")
    types = body.get("types") or []  # list
    tags = body.get("tags") or []
    project = str(body.get("project") or "")
    limit = int(body.get("limit") or 50)
    ix = _open_or_create()
    out = []
    with ix.searcher() as s:
        fields = ["title", "content", "tags"]
        qp = MultifieldParser(fields, schema=ix.schema, group=OrGroup.factory(0.9))
        qstr = _expand_synonyms(q) if q else "*"
        base = qp.parse(qstr)
        flts = []
        if types:
            flts.append(Or([Term("dtype", t) for t in types]))
        if tags:
            for t in tags:
                flts.append(Term("tags", t))
        if project:
            flts.append(Term("project", project))
        if flts:
            q_final = And([base] + flts)
        else:
            q_final = base
        res = s.search(q_final, limit=limit, terms=True)
        for h in res:
            out.append(
                {
                    "id": h["doc_id"],
                    "type": h["dtype"],
                    "title": h["title"],
                    "snippet": h.highlights("content") or "",
                    "tags": h.get("tags", ""),
                    "project": h.get("project", ""),
                    "updated": h.get("updated", 0),
                    "score": float(h.score),
                }
            )
    return {
        "ok": True,
        "items": out,
        "facets": facets(q, {"types": types, "tags": tags, "project": project}),
    }


# Saved searches
def saved_list() -> Dict[str, Any]:
    try:
        data = json.loads(SAVED.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    items = [{"name": k, "query": v} for k, v in data.items()]
    return {"ok": True, "items": items}


def saved_put(name: str, query: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data = json.loads(SAVED.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data[name] = query
    SAVED.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True}


def saved_get(name: str) -> Dict[str, Any]:
    try:
        data = json.loads(SAVED.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    q = data.get(name)
    if q is None:
        return {"ok": False, "error": "not found"}
    return {"ok": True, "query": q}


def saved_delete(name: str) -> Dict[str, Any]:
    try:
        data = json.loads(SAVED.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if name in data:
        del data[name]
        SAVED.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True}
