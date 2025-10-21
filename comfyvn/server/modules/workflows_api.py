import json
import subprocess
import sys
import time
from pathlib import Path

# comfyvn/server/modules/workflows_api.py
from fastapi import APIRouter, Body, HTTPException
from PySide6.QtGui import QAction

router = APIRouter()
WF_DIR = Path("data/workflows")
WF_DIR.mkdir(parents=True, exist_ok=True)
SCENE_DIR = Path("data/scenes")
SCENE_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS = Path("exports/renpy")
EXPORTS.mkdir(parents=True, exist_ok=True)

_job_manager = None


def set_job_manager(jm):  # used by app.py
    global _job_manager
    _job_manager = jm


def _ok(data=None):
    return {"ok": True, **(data or {})}


def _wf_path(name: str) -> Path:
    return WF_DIR / f"{name}.json"


def _scene_path(scene_id: str) -> Path:
    return SCENE_DIR / f"{scene_id}.json"


@router.get("/health")
def health():
    return _ok({"job_manager": bool(_job_manager)})


@router.post("/validate")
def validate_workflow(payload: dict = Body(...)):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid workflow format")
    # basic keys check
    keys = set(payload.keys())
    required = {"name", "title"}
    if not required.issubset(keys):
        return _ok(
            {
                "validated": False,
                "missing": sorted(required - keys),
                "payload_keys": list(keys),
            }
        )
    return _ok({"validated": True, "payload_keys": list(keys)})


@router.post("/put/{name}")
def put_workflow(name: str, payload: dict = Body(...)):
    actual = payload.get("name") or name
    path = _wf_path(actual)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return _ok({"saved": str(path), "name": actual})


def _write_scene(payload: dict) -> Path:
    scene_id = payload.get("name") or payload.get("scene_id") or "draft"
    scene = {
        "scene_id": scene_id,
        "title": payload.get("title") or scene_id,
        "background": payload.get("background") or "",
        "music": payload.get("music") or "",
        "sprites": payload.get("sprites") or [],
        "lines": payload.get("lines") or [],
    }
    if not isinstance(scene["lines"], list):
        scene["lines"] = []
    sp = _scene_path(scene_id)
    sp.write_text(json.dumps(scene, indent=2), encoding="utf-8")
    return sp


def _run_exporter() -> tuple[bool, str]:
    try:
        exe = sys.executable or "python"
        p = subprocess.run(
            [exe, "scripts/export_renpy.py", "--quiet"],
            capture_output=True,
            text=True,
            check=True,
        )
        return True, (p.stdout or "").strip()
    except Exception as e:
        return False, str(e)


@router.post("/instantiate")
def instantiate_workflow(payload: dict = Body(...)):
    sp = _write_scene(payload)
    ok, msg = _run_exporter()
    jid = f"job-{int(time.time())}"
    (WF_DIR / f"done_{jid}.json").write_text(
        json.dumps(
            {
                "job_id": jid,
                "workflow": payload.get("name") or "draft",
                "scene_file": str(sp),
                "export_ok": ok,
                "export_msg": msg,
                "export_dir": str(EXPORTS),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return _ok(
        {
            "job_id": jid,
            "workflow": payload.get("name") or "draft",
            "scene_file": str(sp),
            "export_ok": ok,
            "export_msg": msg,
            "export_dir": str(EXPORTS),
        }
    )


@router.post("/templates/instantiate/")
def instantiate_alias(payload: dict = Body(...)):
    return instantiate_workflow(payload)


@router.get("/list")
def list_workflows():
    files = sorted(p.name for p in WF_DIR.glob("*.json"))
    return {"ok": True, "items": files}
