from __future__ import annotations
from PySide6.QtGui import QAction
from typing import Dict, Any, List, Optional
import json, uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from comfyvn.server.modules.auth import require_scope
from comfyvn.server.core.chat_import import parse_text, apply_alias_map, assign_by_patterns, to_scene_dict

router = APIRouter()
SCENE_DIR = Path("./data/scenes"); SCENE_DIR.mkdir(parents=True, exist_ok=True)

def _write_scene(name: str, data: Dict[str, Any]) -> str:
    p = (SCENE_DIR / f"{name}.json").resolve()
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return name

@router.post("/chat")
async def import_chat(body: Dict[str, Any], _: bool = Depends(require_scope(["content.write"]))):
    text = str(body.get("text") or "")
    if not text.strip(): raise HTTPException(status_code=400, detail="text required")
    fmt = str(body.get("format") or "auto")
    base = str(body.get("name") or f"scene_{uuid.uuid4().hex[:8]}" )
    alias = body.get("alias_map") or {}
    rules = body.get("assign_rules") or []
    split_on = str(body.get("split_on") or "")  # regex boundary to split into scenes
    max_lines = int(body.get("max_lines") or 0)

    # initial parse
    lines = parse_text(text, fmt=fmt)
    lines = apply_alias_map(lines, alias)
    lines = assign_by_patterns(lines, rules)

    # split logic
    scenes: List[List[dict]] = []
    if split_on:
        import re as _re
        current: List[dict] = []
        rgx = _re.compile(split_on, _re.IGNORECASE)
        for ln in lines:
            if rgx.search(ln.text):
                if current: scenes.append(current); current = []
                continue
            current.append(ln)
        if current: scenes.append(current)
    elif max_lines and max_lines>0:
        current: List[dict] = []
        for ln in lines:
            current.append(ln)
            if len(current) >= max_lines:
                scenes.append(current); current = []
        if current: scenes.append(current)
    else:
        scenes = [lines]

    created = []
    for i, seq in enumerate(scenes):
        name = base if len(scenes)==1 else f"{base}_{i+1:02d}"
        data = to_scene_dict(name, seq)
        _write_scene(name, data)
        created.append(name)
    return {"ok": True, "created": created, "count": len(created)}