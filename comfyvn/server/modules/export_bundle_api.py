import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from PySide6.QtGui import QAction

from comfyvn.core.policy_gate import policy_gate
from comfyvn.core.provenance import stamp_path

# comfyvn/server/modules/export_bundle_api.py


router = APIRouter()
REN = Path("exports/renpy")
BUNDLES = Path("exports/bundles")
REN.mkdir(parents=True, exist_ok=True)
BUNDLES.mkdir(parents=True, exist_ok=True)


@router.get("/health")
def health():
    return {"ok": True, "renpy_exists": REN.exists()}


@router.post("/bundle/renpy")
def bundle_renpy():
    gate = policy_gate.evaluate_action("export.bundle")
    if gate.get("requires_ack") and not gate.get("allow"):
        raise HTTPException(
            status_code=423,
            detail={
                "message": "export blocked until legal acknowledgement is recorded",
                "gate": gate,
            },
        )
    ts = int(time.time())
    base = BUNDLES / f"renpy_{ts}"
    # shutil.make_archive adds extension automatically for format="zip"
    shutil.make_archive(str(base), "zip", REN)
    zip_path = str(base) + ".zip"
    provenance = stamp_path(
        zip_path,
        source="api.export.bundle",
        inputs={"bundle": "renpy", "timestamp": ts},
        embed=False,
    )
    return {"ok": True, "zip": zip_path, "provenance": provenance, "gate": gate}
