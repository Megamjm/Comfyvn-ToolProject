from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from PySide6.QtGui import QAction

from comfyvn.core.policy_gate import policy_gate
from comfyvn.core.provenance import stamp_path
from comfyvn.policy.enforcer import policy_enforcer

router = APIRouter()
OUT = Path("exports/renpy")
OUT.mkdir(parents=True, exist_ok=True)

LOGGER = logging.getLogger("comfyvn.api.export.scene")


@router.post("/export/scene")
def export_scene(payload: dict = Body(...)):
    from comfyvn.server.modules.scene_api import _scene_path

    sid = payload.get("scene")
    if not sid:
        return {"ok": False, "error": "scene required"}
    gate = policy_gate.evaluate_action("export.scene")
    if gate.get("requires_ack"):
        LOGGER.warning("Advisory disclaimer pending for export.scene")
    src = _scene_path(sid)
    if not src.exists():
        return {"ok": False, "error": "scene not found"}
    data = json.loads(src.read_text(encoding="utf-8"))
    out = OUT / f"{sid}.rpy"
    bundle_payload = {
        "project_id": None,
        "timeline_id": None,
        "scenes": {sid: data},
        "scene_sources": {sid: src.as_posix()},
        "metadata": {"source": "export.scene", "scene_id": sid},
    }
    enforcement = policy_enforcer.enforce(
        "export.scene", bundle_payload, source="export.scene"
    )
    if not enforcement.allow:
        raise HTTPException(
            status_code=423,
            detail={
                "message": "policy enforcement blocked",
                "result": enforcement.to_dict(),
            },
        )
    with out.open("w", encoding="utf-8") as f:
        f.write(f"label {sid}:\n")
        for entry in data.get("dialogue", []):
            f.write(f'    "{entry.get("speaker")}": "{entry.get("text")}"\n')
    provenance = stamp_path(
        out,
        source="api.export.scene",
        inputs={"scene_id": sid, "line_count": len(data.get("dialogue", []))},
        embed=False,
    )
    return {
        "ok": True,
        "file": str(out),
        "provenance": provenance,
        "gate": gate,
        "enforcement": enforcement.to_dict(),
    }
