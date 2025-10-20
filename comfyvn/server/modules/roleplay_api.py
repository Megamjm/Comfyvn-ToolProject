from __future__ import annotations

import re
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from comfyvn.server.core.storage import list_scenes, scene_load, scene_save

router = APIRouter()

def _parse_transcript(text: str) -> List[Dict[str, Any]]:
    lines=[]
    for raw in (text or "").splitlines():
        s=raw.strip()
        if not s: continue
        m=re.match(r"([^:]{1,64}):\s*(.*)$", s)
        if m:
            spk=m.group(1).strip()
            txt=m.group(2).strip()
        else:
            spk="Narrator"; txt=s
        lines.append({"speaker": spk, "text": txt})
    return lines

@router.get("/scenes")
async def scenes():
    return {"ok": True, "items": list_scenes()}

@router.get("/scene")
async def get_scene(scene_id: str):
    return {"ok": True, "scene": scene_load(scene_id)}

@router.post("/import")
async def import_transcript(body: Dict[str, Any]):
    scene_id=str(body.get("scene_id") or "imported")
    text=str(body.get("transcript") or "")
    if not text:
        raise HTTPException(400, "missing transcript")
    lines=_parse_transcript(text)
    saved=scene_save({"scene_id": scene_id, "lines": lines})
    return {"ok": True, "scene": saved, "count": len(lines)}

@router.post("/mass-edit")
async def mass_edit(body: Dict[str, Any]):
    scene_id=str(body.get("scene_id") or "")
    if not scene_id: raise HTTPException(400, "missing scene_id")
    ops=list(body.get("ops") or [])
    sc=scene_load(scene_id); L=sc["lines"]

    def rename_speaker(frm, to):
        for ln in L:
            if ln.get("speaker")==frm: ln["speaker"]=to

    def set_speaker_by_indices(indices, to):
        idx=set(int(i) for i in (indices or []) if isinstance(i,(int,str)))
        for i in idx:
            if 0<=i<len(L): L[i]["speaker"]=to

    def replace_text(find, repl, *, ignore_case=False):
        flags=re.IGNORECASE if ignore_case else 0
        rx=re.compile(str(find), flags)
        for ln in L:
            ln["text"]=rx.sub(str(repl), ln.get("text",""))

    def move_range(start, end, to_index):
        i=max(0,int(start)); j=min(len(L),int(end)); k=max(0,min(len(L),int(to_index)))
        if i>=j: return
        chunk=L[i:j]; del L[i:j]
        if k>i: k -= (j-i)
        for n,ln in enumerate(chunk):
            L.insert(k+n, ln)

    for op in ops:
        t=(op.get("op") or "").lower()
        if t=="rename_speaker":
            rename_speaker(op.get("from"), op.get("to"))
        elif t=="set_speaker_by_indices":
            set_speaker_by_indices(op.get("indices"), op.get("to"))
        elif t=="replace_text":
            replace_text(op.get("find",""), op.get("replace",""), ignore_case=bool(op.get("ignore_case")))
        elif t=="move_range":
            move_range(op.get("start",0), op.get("end",0), op.get("to_index",0))
        else:
            # ignore unknown ops
            pass

    saved=scene_save({"scene_id": scene_id, "lines": L})
    return {"ok": True, "scene": saved, "lines": len(L)}