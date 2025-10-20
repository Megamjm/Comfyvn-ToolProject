from PySide6.QtGui import QAction
from fastapi import APIRouter, Body
from pathlib import Path
import json, time, difflib

router = APIRouter()

DATA = Path("data/scenes")
AUDIT = Path("data/audit/mass_edits"); AUDIT.mkdir(parents=True, exist_ok=True)

@router.post("/preview")
def preview_edits(rules: dict = Body(...)):
    previews = []
    for p in DATA.glob("*.json"):
        text = p.read_text(encoding="utf-8")
        for k, v in rules.get("replace", {}).items():
            text = text.replace(k, v)
        previews.append({"scene": p.name, "diff": list(difflib.unified_diff(
            p.read_text().splitlines(), text.splitlines(), lineterm=""
        ))})
    return {"ok": True, "previews": previews}

@router.post("/commit")
def commit_edits(rules: dict = Body(...)):
    results = []
    for p in DATA.glob("*.json"):
        j = json.loads(p.read_text(encoding="utf-8"))
        changed = False
        for ln in j.get("lines", []):
            spk = ln.get("speaker", "")
            if spk in rules.get("rename", {}):
                ln["speaker"] = rules["rename"][spk]; changed = True
        if changed:
            p.write_text(json.dumps(j, indent=2, ensure_ascii=False))
            results.append(p.name)
    audit = AUDIT / f"massedit_{int(time.time())}.json"
    audit.write_text(json.dumps({"rules": rules, "results": results}, indent=2))
    return {"ok": True, "edited": results}