from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from PySide6.QtGui import QAction

from comfyvn.core.policy_gate import policy_gate
from comfyvn.core.provenance import stamp_path

router = APIRouter()
OUT = Path("exports/renpy")
OUT.mkdir(parents=True, exist_ok=True)


@router.post("/export/scene")
def export_scene(payload: dict = Body(...)):
    from comfyvn.server.modules.scene_api import _scene_path

    sid = payload.get("scene")
    if not sid:
        return {"ok": False, "error": "scene required"}
    gate = policy_gate.evaluate_action("export.scene")
    if gate.get("requires_ack") and not gate.get("allow"):
        raise HTTPException(
            status_code=423,
            detail={
                "message": "export blocked until legal acknowledgement is recorded",
                "gate": gate,
            },
        )
    src = _scene_path(sid)
    if not src.exists():
        return {"ok": False, "error": "scene not found"}
    data = json.loads(src.read_text(encoding="utf-8"))
    out = OUT / f"{sid}.rpy"
    with out.open("w", encoding="utf-8") as f:
        f.write(f"label {sid}:\n")
        for l in data.get("dialogue", []):
            f.write(f'    "{l.get("speaker")}": "{l.get("text")}"\n')
    provenance = stamp_path(
        out,
        source="api.export.scene",
        inputs={"scene_id": sid, "line_count": len(data.get("dialogue", []))},
        embed=False,
    )
    return {"ok": True, "file": str(out), "provenance": provenance, "gate": gate}
