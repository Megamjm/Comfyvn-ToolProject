from __future__ import annotations
from PySide6.QtGui import QAction
import json, re, copy, difflib, time
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple
from pathlib import Path

DATA = Path("./data"); DATA.mkdir(parents=True, exist_ok=True)
SCENES = DATA / "scenes"; SCENES.mkdir(parents=True, exist_ok=True)
HIST = DATA / "mass_edit"; HIST.mkdir(parents=True, exist_ok=True)
RULES = HIST / "rules.json"

def _load_scene(scene_id: str) -> Dict[str, Any]:
    p = SCENES / f"{scene_id}.json"
    if not p.exists(): return {"scene_id": scene_id, "title": scene_id, "lines": []}
    try: return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception: return {"scene_id": scene_id, "title": scene_id, "lines": []}

def _save_scene(scene: Dict[str, Any]):
    p = SCENES / f"{scene.get('scene_id','scene')}.json"
    p.write_text(json.dumps(scene, indent=2, ensure_ascii=False), encoding="utf-8")

def _history_path(scene_id: str) -> Path:
    return HIST / f"history_{scene_id}.json"

def _load_hist(scene_id: str) -> Dict[str, Any]:
    hp = _history_path(scene_id)
    if hp.exists():
        try: return json.loads(hp.read_text(encoding="utf-8"))
        except Exception: pass
    return {"stack": [], "idx": -1}

def _save_hist(scene_id: str, hist: Dict[str, Any]):
    _history_path(scene_id).write_text(json.dumps(hist, indent=2), encoding="utf-8")

def _push_history(scene: Dict[str, Any]):
    sid = scene.get("scene_id","scene")
    h = _load_hist(sid)
    # drop redo tail
    if h["idx"] < len(h["stack"]) - 1:
        h["stack"] = h["stack"][:h["idx"]+1]
    h["stack"].append({"ts": time.time(), "scene": copy.deepcopy(scene)})
    # cap size
    if len(h["stack"]) > 50: h["stack"] = h["stack"][-50:]
    h["idx"] = len(h["stack"]) - 1
    _save_hist(sid, h)

def _select_indices(lines: List[Dict[str,Any]], sel: Dict[str,Any] | None) -> List[int]:
    if not sel: return list(range(len(lines)))
    idxs = set(range(len(lines)))
    if "indices" in sel and isinstance(sel["indices"], list):
        idxs = idxs.intersection(i for i in sel["indices"] if 0 <= i < len(lines))
    if "range" in sel and isinstance(sel["range"], list) and len(sel["range"])==2:
        a, b = int(sel["range"][0]), int(sel["range"][1])
        idxs = idxs.intersection(set(i for i in range(max(0,a), min(len(lines), b))))
    if "speakers" in sel and sel["speakers"]:
        ok = {s.strip() for s in sel["speakers"]}
        idxs = set(i for i in idxs if str(lines[i].get("speaker","")) in ok)
    if "contains" in sel and sel["contains"]:
        s = str(sel["contains"])
        idxs = set(i for i in idxs if s in str(lines[i].get("text","")))
    if "regex" in sel and sel["regex"]:
        pat = re.compile(sel["regex"], re.I if sel.get("flags","").lower().find("i")>=0 else 0)
        idxs = set(i for i in idxs if pat.search(str(lines[i].get("text",""))))
    if sel.get("invert"):  # invert selection
        all_idx = set(range(len(lines)))
        idxs = all_idx - idxs
    return sorted(list(idxs))

def _apply_op(lines: List[Dict[str,Any]], op: Dict[str,Any], ctx: Dict[str,Any]) -> Tuple[List[Dict[str,Any]], int]:
    typ = op.get("type")
    sel = op.get("select") or {}
    idxs = _select_indices(lines, sel)
    changed = 0
    if typ == "regex_replace":
        pat = re.compile(op.get("pattern",""), re.I if op.get("flags","").lower().find("i")>=0 else 0)
        repl = op.get("repl","")
        for i in idxs:
            t = str(lines[i].get("text",""))
            nt, n = pat.subn(repl, t)
            if n>0:
                lines[i]["text"] = nt; changed += n
    elif typ == "change_speaker":
        to = op.get("to","")
        for i in idxs:
            if lines[i].get("speaker") != to:
                lines[i]["speaker"] = to; changed += 1
    elif typ == "delete":
        # delete selected indices
        for i in sorted(idxs, reverse=True):
            lines.pop(i); changed += 1
    elif typ == "move_range":
        a = int(op.get("start") or 0); cnt = int(op.get("count") or 0); to = int(op.get("to") or 0)
        if cnt>0 and 0<=a<len(lines):
            block = lines[a:a+cnt]; del lines[a:a+cnt]
            to = max(0, min(len(lines), to))
            for j, row in enumerate(block):
                lines.insert(to+j, row)
            changed += len(block)
    elif typ == "normalize_ws":
        for i in idxs:
            t = lines[i].get("text","")
            nt = re.sub(r"\s+", " ", t).strip()
            if nt != t:
                lines[i]["text"] = nt; changed += 1
    elif typ == "prefix":
        val = str(op.get("value") or "")
        for i in idxs:
            lines[i]["text"] = val + str(lines[i].get("text","")); changed += 1
    elif typ == "suffix":
        val = str(op.get("value") or "")
        for i in idxs:
            lines[i]["text"] = str(lines[i].get("text","")) + val; changed += 1
    elif typ == "timestamp_offset":
        off = float(op.get("offset") or 0.0)
        scale = float(op.get("scale") or 1.0)
        for i in idxs:
            ts = float(lines[i].get("ts") or 0.0)
            nts = ts * scale + off
            lines[i]["ts"] = nts; changed += 1
    elif typ == "merge_consecutive_by_speaker":
        sep = str(op.get("sep") or " ")
        new = []
        i = 0
        while i < len(lines):
            cur = lines[i]; j = i+1
            while j < len(lines) and lines[j].get("speaker")==cur.get("speaker"):
                cur["text"] = str(cur.get("text","")) + sep + str(lines[j].get("text",""))
                j += 1; changed += 1
            new.append(cur); i = j
        lines[:] = new
    elif typ == "reorder":
        order = op.get("order") or []
        if isinstance(order, list) and len(order)==len(lines):
            new = [lines[i] for i in order]
            lines[:] = new
            changed += len(lines)
    elif typ == "split_by_punct":
        pat = re.compile(op.get("pattern") or r"[.!?]\s+")
        new = []
        for k, row in enumerate(lines):
            if k in idxs:
                tx = str(row.get("text",""))
                parts = [p for p in pat.split(tx) if p.strip()]
                if len(parts) <= 1:
                    new.append(row)
                else:
                    for p in parts:
                        nr = dict(row); nr["text"] = p.strip(); new.append(nr)
                        changed += 1
            else:
                new.append(row)
        lines[:] = new
    else:
        # unknown op: no-op
        pass
    return lines, changed

def apply_ops(scene_id: str, ops: List[Dict[str,Any]], ctx: Dict[str,Any] | None = None, save_history: bool = True) -> Dict[str,Any]:
    scene = _load_scene(scene_id)
    before_lines = [f"{l.get('speaker','')}: {l.get('text','')}" for l in (scene.get("lines") or [])]
    lines = [dict(l) for l in (scene.get("lines") or [])]
    total_changes = 0
    for op in ops or []:
        lines, c = _apply_op(lines, op, ctx or {})
        total_changes += c
    new_scene = dict(scene); new_scene["lines"] = lines
    # diff
    after_lines = [f"{l.get('speaker','')}: {l.get('text','')}" for l in lines]
    diff = "\n".join(difflib.unified_diff(before_lines, after_lines, fromfile="before", tofile="after", lineterm=""))
    if save_history and total_changes>0:
        _push_history(scene)  # push snapshot before change
        _save_scene(new_scene)
    return {"ok": True, "changes": int(total_changes), "diff": diff, "scene": new_scene}

def preview(scene_id: str, ops: List[Dict[str,Any]], ctx: Dict[str,Any] | None = None) -> Dict[str,Any]:
    scene = _load_scene(scene_id)
    before_lines = [f"{l.get('speaker','')}: {l.get('text','')}" for l in (scene.get("lines") or [])]
    lines = [dict(l) for l in (scene.get("lines") or [])]
    total_changes = 0
    for op in ops or []:
        lines, c = _apply_op(lines, op, ctx or {})
        total_changes += c
    after_lines = [f"{l.get('speaker','')}: {l.get('text','')}" for l in lines]
    diff = "\n".join(difflib.unified_diff(before_lines, after_lines, fromfile="before", tofile="after", lineterm=""))
    return {"ok": True, "changes": int(total_changes), "diff": diff}

def undo(scene_id: str) -> Dict[str,Any]:
    h = _load_hist(scene_id)
    if h["idx"] < 0: return {"ok": False, "error": "nothing to undo"}
    cur_idx = h["idx"]
    snap = h["stack"][cur_idx]["scene"]
    # restore snapshot
    _save_scene(snap)
    h["idx"] -= 1
    _save_hist(scene_id, h)
    return {"ok": True, "restored": snap.get("scene_id")}

def redo(scene_id: str) -> Dict[str,Any]:
    h = _load_hist(scene_id)
    if h["idx"] >= len(h["stack"]) - 1: return {"ok": False, "error": "nothing to redo"}
    h["idx"] += 1
    snap = h["stack"][h["idx"]]["scene"]
    _save_scene(snap)
    _save_hist(scene_id, h)
    return {"ok": True, "restored": snap.get("scene_id")}

def history(scene_id: str) -> Dict[str,Any]:
    h = _load_hist(scene_id)
    items = [{"i": i, "ts": it.get("ts")} for i, it in enumerate(h.get("stack",[]))]
    return {"ok": True, "len": len(items), "idx": h.get("idx",-1), "items": items}

# Rule library
def rules_list() -> Dict[str,Any]:
    try: data = json.loads(RULES.read_text(encoding="utf-8"))
    except Exception: data = {}
    return {"ok": True, "items": [{"name": k, "ops": v} for k,v in data.items()]}

def rules_put(name: str, ops: List[Dict[str,Any]]):
    try: data = json.loads(RULES.read_text(encoding="utf-8"))
    except Exception: data = {}
    data[name] = ops
    RULES.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}

def rules_get(name: str):
    try: data = json.loads(RULES.read_text(encoding="utf-8"))
    except Exception: data = {}
    ops = data.get(name)
    if ops is None: return {"ok": False, "error": "not found"}
    return {"ok": True, "ops": ops}

def rules_delete(name: str):
    try: data = json.loads(RULES.read_text(encoding="utf-8"))
    except Exception: data = {}
    if name in data: del data[name]; RULES.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}