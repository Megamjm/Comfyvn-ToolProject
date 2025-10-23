from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from whoosh import index
    from whoosh.analysis import StemmingAnalyzer
    from whoosh.fields import DATETIME, ID, KEYWORD, NUMERIC, TEXT, Schema
    from whoosh.qparser import MultifieldParser, OrGroup
    from whoosh.query import And, Or, Term

    WHOOSH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    index = None  # type: ignore[assignment]
    StemmingAnalyzer = None  # type: ignore[assignment]
    Schema = None  # type: ignore[assignment]
    MultifieldParser = None  # type: ignore[assignment]
    OrGroup = None  # type: ignore[assignment]
    And = Or = Term = None  # type: ignore[assignment]
    WHOOSH_AVAILABLE = False

from comfyvn.core.db_manager import DEFAULT_DB_PATH
from comfyvn.studio.core import AssetRegistry, CharacterRegistry, SceneRegistry

DATA_DIR = Path("./data/search")
DATA_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DIR = DATA_DIR / "index"
MANIFEST = DATA_DIR / "manifest.json"
SAVED = DATA_DIR / "saved.json"

if WHOOSH_AVAILABLE:  # pragma: no branch - schema defined only when available
    SCHEMA = Schema(
        doc_id=ID(stored=True, unique=True),
        dtype=KEYWORD(stored=True, lowercase=True, commas=True),
        title=TEXT(stored=True, analyzer=StemmingAnalyzer()),
        content=TEXT(analyzer=StemmingAnalyzer()),
        tags=KEYWORD(lowercase=True, commas=True, scorable=True, stored=True),
        project=ID(stored=True),
        updated=NUMERIC(stored=True, sortable=True),
    )
else:
    SCHEMA = None

SYN = {
    "dialog": ["dialogue", "conversation", "chat"],
    "scene": ["chapter", "episode"],
    "character": ["persona", "actor"],
    "persona": ["character", "profile"],
    "asset": ["resource", "file"],
    "import": ["ingest", "upload"],
}


def _hash(o: Any) -> str:
    return hashlib.sha256(
        json.dumps(o, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _load(
    db_url_env: str | None = None,
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    # scenes, characters
    scenes, chars = [], []
    assets: List[Dict[str, Any]] = []
    personas: List[Dict[str, Any]] = []
    # Prefer DB when configured
    use_db = bool(os.getenv("DB_URL", "").strip())
    if use_db:
        try:
            from sqlalchemy.orm import Session

            from comfyvn.server.core.db import CharacterRow, SceneRow, get_db, init_db

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
    # Registry-backed datasets (scenes/characters/assets) across all projects.
    for project_id in _list_project_ids():
        try:
            sreg = SceneRegistry(project_id=project_id)
            for entry in sreg.list_scenes():
                scene = sreg.get_scene(entry["id"])
                if not scene:
                    continue
                meta = _ensure_dict(scene.get("meta") or entry.get("meta"))
                payload = {
                    "scene_id": f"scene-{project_id}-{entry['id']}",
                    "id": entry["id"],
                    "title": scene.get("title") or entry.get("title"),
                    "body": scene.get("body") or "",
                    "meta": meta,
                    "tags": _normalise_tag_list(meta.get("tags") or []),
                    "project_id": project_id,
                    "__project": project_id,
                }
                payload["__updated"] = _coerce_timestamp(
                    payload["meta"].get("updated_at")
                    or payload["meta"].get("updated")
                    or payload["meta"].get("timestamp")
                )
                scenes.append(payload)
        except Exception:
            pass

        try:
            creg = CharacterRegistry(project_id=project_id)
            for entry in creg.list_characters():
                meta = _ensure_dict(entry.get("meta"))
                payload = {
                    "name": entry.get("name") or f"character-{entry.get('id')}",
                    "traits": _ensure_dict(entry.get("traits")),
                    "meta": meta,
                    "project_id": project_id,
                    "__project": project_id,
                }
                payload["__updated"] = _coerce_timestamp(meta.get("updated_at"))
                chars.append(payload)
        except Exception:
            pass

        try:
            areg = AssetRegistry(project_id=project_id)
            for asset in areg.list_assets(limit=None):
                asset = dict(asset)
                asset["__project"] = project_id
                meta = _ensure_dict(asset.get("meta"))
                timestamp = (
                    meta.get("updated_at")
                    or meta.get("timestamp")
                    or asset.get("created_at")
                )
                asset["__updated"] = _coerce_timestamp(timestamp)
                assets.append(asset)
        except Exception:
            pass

    personas.extend(_load_personas())

    return scenes, chars, assets, personas


def _doc_from_scene(s: Dict[str, Any]) -> Dict[str, Any]:
    sid = s.get("scene_id") or s.get("id") or _hash(s)[:12]
    project = (
        s.get("__project")
        or s.get("project_id")
        or _project_from_tags(s.get("tags") or [])
    )
    doc_id = f"scene:{project}:{sid}" if project else f"scene:{sid}"
    title = s.get("title") or sid
    lines = s.get("lines") or []
    if lines:
        content = "\n".join(str(x.get("text") or "") for x in lines)
    else:
        body = s.get("body")
        if isinstance(body, str) and body.strip():
            content = body
        else:
            content = json.dumps(s.get("meta") or {}, ensure_ascii=False)
    tags = s.get("tags") or []
    meta = s.get("meta") or {}
    if isinstance(meta, dict):
        tags.extend(meta.get("tags") or [])
    tags = _normalise_tag_list(tags)
    return dict(
        doc_id=doc_id,
        dtype="scene",
        title=title,
        content=content[:100000],
        tags=",".join(tags),
        project=str(project or ""),
        updated=int(s.get("__updated") or time.time()),
    )


def _doc_from_char(c: Dict[str, Any]) -> Dict[str, Any]:
    project = c.get("__project") or c.get("project_id")
    name = c.get("name") or c.get("id") or _hash(c)[:12]
    bio = c.get("bio") or c.get("desc") or ""
    tags = _normalise_tag_list(c.get("tags") or [])
    return dict(
        doc_id=f"character:{project}:{name}" if project else f"character:{name}",
        dtype="character",
        title=name,
        content=bio or json.dumps(c.get("traits") or {}, ensure_ascii=False),
        tags=",".join(tags),
        project=str(project or ""),
        updated=int(c.get("__updated") or time.time()),
    )


def _doc_from_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    uid = asset.get("uid") or _hash(asset)[:12]
    project = asset.get("__project") or asset.get("project_id")
    doc_id = f"asset:{project}:{uid}" if project else f"asset:{uid}"
    meta = _ensure_dict(asset.get("meta"))
    title = (
        meta.get("title") or meta.get("name") or Path(str(asset.get("path", uid))).name
    )
    tags = _normalise_tag_list(
        meta.get("tags") or meta.get("style_tags") or meta.get("keywords") or []
    )
    tags.extend([asset.get("type") or ""])
    tags = _normalise_tag_list(tags)
    content_parts: List[str] = [str(asset.get("path") or "")]
    if meta:
        content_parts.append(json.dumps(meta, ensure_ascii=False))
    content = "\n".join(filter(None, content_parts))
    return dict(
        doc_id=doc_id,
        dtype="asset",
        title=title,
        content=content[:80000],
        tags=",".join(filter(None, tags)),
        project=str(project or ""),
        updated=int(asset.get("__updated") or time.time()),
    )


def _doc_from_persona(persona: Dict[str, Any]) -> Dict[str, Any]:
    project = persona.get("__project") or persona.get("project_id")
    pid = persona.get("id") or persona.get("slug")
    if not pid:
        pid = _slugify(persona.get("displayName") or persona.get("name"))
    doc_id = f"persona:{project}:{pid}" if project else f"persona:{pid}"
    title = persona.get("displayName") or persona.get("name") or pid
    tags = _normalise_tag_list(
        persona.get("tags")
        or persona.get("tagset", {}).get("general")
        or persona.get("tagset", {}).get("style")
        or []
    )
    bio_parts: List[str] = []
    for field in ("summary", "description", "personality", "backstory"):
        value = persona.get(field)
        if isinstance(value, str):
            bio_parts.append(value)
    lore = persona.get("lore")
    if isinstance(lore, dict):
        bio_parts.append(json.dumps(lore, ensure_ascii=False))
    content = "\n".join(filter(None, bio_parts)) or json.dumps(
        persona, ensure_ascii=False
    )
    updated = persona.get("__updated") or time.time()
    return dict(
        doc_id=doc_id,
        dtype="persona",
        title=title,
        content=content[:100000],
        tags=",".join(filter(None, tags)),
        project=str(project or ""),
        updated=int(updated),
    )


def _project_from_tags(tags: List[str]) -> str | None:
    for t in tags or []:
        if t.startswith("project:"):
            return t.split(":", 1)[1]
    return None


def _open_or_create():
    _require_whoosh()
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
    _require_whoosh()
    scenes, chars, assets, personas = _load()
    docs = (
        [_doc_from_scene(s) for s in scenes]
        + [_doc_from_char(c) for c in chars]
        + [_doc_from_asset(a) for a in assets]
        + [_doc_from_persona(p) for p in personas]
    )
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
    _require_whoosh()
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
    _require_whoosh()
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


def _require_whoosh() -> None:
    if not WHOOSH_AVAILABLE:
        raise RuntimeError(
            "Whoosh search backend is not installed. Install 'whoosh' to enable search."
        )


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: Any, default: str = "persona") -> str:
    text = str(value or "").strip().lower()
    slug = _SLUG_RE.sub("-", text).strip("-")
    return slug or default


def _ensure_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def _normalise_tag_list(values: Iterable[Any]) -> List[str]:
    tags: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            tags.extend(_normalise_tag_list(value))
            continue
        text = str(value).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(text)
    return tags


def _coerce_timestamp(value: Any) -> int:
    if value is None:
        return int(time.time())
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return int(time.time())
        try:
            return int(float(text))
        except ValueError:
            try:
                return int(datetime.fromisoformat(text).timestamp())
            except ValueError:
                pass
    return int(time.time())


def _list_project_ids() -> List[str]:
    projects: set[str] = set()
    db_path = DEFAULT_DB_PATH
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            tables = (
                "projects",
                "scenes",
                "characters",
                "assets_registry",
                "timelines",
                "worlds",
            )
            for table in tables:
                try:
                    cursor = conn.execute(
                        f"SELECT DISTINCT project_id FROM {table} WHERE project_id IS NOT NULL"
                    )
                    for row in cursor.fetchall():
                        pid = row[0]
                        if pid:
                            projects.add(str(pid))
                except sqlite3.Error:
                    continue
        except sqlite3.Error:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
    if not projects:
        projects.add("default")
    return sorted(projects)


def _load_personas() -> List[Dict[str, Any]]:
    personas: List[Dict[str, Any]] = []

    def _load_dir(root: Path, project_hint: Optional[str] = None) -> None:
        if not root.exists():
            return
        for path in root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            payload["__project"] = project_hint or payload.get("project_id")
            payload["__updated"] = _coerce_timestamp(path.stat().st_mtime)
            personas.append(payload)

    global_dir = Path("data/personas")
    _load_dir(global_dir)

    projects_root = Path("data/projects")
    if projects_root.exists():
        for proj_dir in projects_root.iterdir():
            if not proj_dir.is_dir():
                continue
            project_id = proj_dir.name
            _load_dir(proj_dir / "personas", project_id)

    return personas


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
