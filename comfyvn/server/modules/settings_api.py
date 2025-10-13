# comfyvn/server/modules/settings_api.py
# ⚙️ Settings API — ComfyVN v3.1.1 Unified Sync (Core + GUI)
# Provides: /settings, /settings/save, /settings/reload, /settings/schema
# [Server Core Production Chat | Project Integration Alignment]

from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/settings", tags=["Settings"])

CONFIG_PATH = Path("./comfyvn/data/settings_overrides.json")
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------------------------
# 🔧 Helpers
# -------------------------------------------------------------------
def _manager(request: Request):
    """Return settings manager instance or None."""
    return getattr(request.app.state, "settings_manager", None)


# -------------------------------------------------------------------
# 🔍 Status
# -------------------------------------------------------------------
@router.get("/status")
async def status(request: Request):
    mgr = _manager(request)
    return {
        "ok": True,
        "has_manager": bool(mgr),
        "path": str(CONFIG_PATH.resolve()),
        "exists": CONFIG_PATH.exists(),
    }


# -------------------------------------------------------------------
# 📖 Get current settings
# -------------------------------------------------------------------
@router.get("/")
async def get_settings(request: Request):
    mgr = _manager(request)
    if mgr and hasattr(mgr, "dump"):
        try:
            return {"ok": True, "source": "manager", "settings": mgr.dump()}
        except Exception as e:
            raise HTTPException(500, f"Manager dump failed: {e}")

    # fallback to file
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return {"ok": True, "source": "file", "settings": json.load(f)}
        except Exception as e:
            raise HTTPException(500, f"Read failed: {e}")

    return {"ok": True, "source": "default", "settings": {}}


# -------------------------------------------------------------------
# 💾 Save settings
# -------------------------------------------------------------------
@router.post("/save")
async def save_settings(request: Request):
    mgr = _manager(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    if not isinstance(payload, dict):
        raise HTTPException(400, "Payload must be an object")

    # manager path preferred
    if mgr and hasattr(mgr, "set_many"):
        try:
            res = mgr.set_many(payload)
            return {"ok": True, "source": "manager", "settings": res}
        except Exception as e:
            raise HTTPException(500, f"Manager set_many failed: {e}")

    # fallback: file write
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return {"ok": True, "source": "file", "path": str(CONFIG_PATH.resolve())}
    except Exception as e:
        raise HTTPException(500, f"Save failed: {e}")


# -------------------------------------------------------------------
# 🔄 Reload settings
# -------------------------------------------------------------------
@router.get("/reload")
async def reload_settings(request: Request):
    mgr = _manager(request)
    if mgr and hasattr(mgr, "set_many"):
        try:
            mgr.set_many({})  # triggers refresh from file
            return {"ok": True, "reloaded": True, "source": "manager"}
        except Exception as e:
            raise HTTPException(500, f"Manager reload failed: {e}")

    # fallback noop
    return {"ok": True, "reloaded": False, "source": "file"}


# -------------------------------------------------------------------
# 🧩 Schema for GUI auto-generation
# -------------------------------------------------------------------
@router.get("/schema")
async def schema(request: Request):
    mgr = _manager(request)
    try:
        from comfyvn.core.settings_manager import Settings

        return {"ok": True, "schema": Settings.model_json_schema()}
    except Exception as e:
        raise HTTPException(500, f"Schema generation failed: {e}")
