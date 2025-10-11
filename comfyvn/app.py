# comfyvn/app.py
# ⚙️ ComfyVN Server Core
# Version: 1.1.2 (GUI Integration)
# Date: 2025-10-10
# [Code Updates Chat + GUI Integration Sync]

from __future__ import annotations
import os, json, asyncio, subprocess
from pathlib import Path
from typing import Any, Dict, Optional
import httpx, uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings

# -----------------------------------------------------
# Settings
# -----------------------------------------------------
class Settings(BaseSettings):
    APP_NAME: str = "ComfyVN Server Core"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    COMFYUI_BASE: str = "http://127.0.0.1:8188"
    LMSTUDIO_BASE: str = "http://127.0.0.1:1234/v1"
    PROJECT_ROOT: Path = Path(__file__).parent.resolve()
    DATA_DIR: Path = Field(default_factory=lambda: Path("./data").resolve())
    WORKFLOWS_DIR: Path = Field(default_factory=lambda: Path("./workflows").resolve())
    EXPORTS_DIR: Path = Field(default_factory=lambda: Path("./exports").resolve())

    class Config:
        env_file = ".env"
        case_sensitive = True

    @validator("DATA_DIR", "WORKFLOWS_DIR", "EXPORTS_DIR", pre=True)
    def _ensure_path(cls, v):  # type: ignore
        return Path(v).resolve()

settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
settings.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------
# FastAPI App
# -----------------------------------------------------
app = FastAPI(title=settings.APP_NAME, version="1.1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------
# Module Imports
# -----------------------------------------------------
from comfyvn.modules.scene_preprocessor import preprocess_scene
from comfyvn.modules.mode_manager import ModeManager

# -----------------------------------------------------
# HTTPX Client
# -----------------------------------------------------
_client: Optional[httpx.AsyncClient] = None

@app.on_event("startup")
async def _startup() -> None:
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=60.0))

@app.on_event("shutdown")
async def _shutdown() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None

def _get_client() -> httpx.AsyncClient:
    if not _client:
        raise RuntimeError("HTTP client not initialized")
    return _client

# -----------------------------------------------------
# ComfyUI Helpers
# -----------------------------------------------------
async def comfyui_health() -> Dict[str, Any]:
    client = _get_client()
    r = await client.get(f"{settings.COMFYUI_BASE}/system_stats")
    r.raise_for_status()
    return r.json()

async def comfyui_queue_prompt(payload: Dict[str, Any]) -> Dict[str, Any]:
    client = _get_client()
    r = await client.post(f"{settings.COMFYUI_BASE}/prompt", json=payload)
    r.raise_for_status()
    return r.json()

# -----------------------------------------------------
# Bridge + Managers
# -----------------------------------------------------
class ComfyUIBridge:
    async def queue_render(self, payload: dict):
        return await comfyui_queue_prompt(payload)

mode_manager = ModeManager()
comfy_bridge = ComfyUIBridge()

# -----------------------------------------------------
# Routes
# -----------------------------------------------------
@app.get("/")
async def root():
    return {"status": "ComfyVN Server Online", "current_mode": mode_manager.get_mode()}

@app.get("/mode/list")
async def list_modes():
    return {"available_modes": mode_manager.list_modes()}

@app.post("/mode/set")
async def set_mode(data: dict):
    try:
        new_mode = data.get("mode")
        mode_manager.set_mode(new_mode)
        return {"success": True, "mode": mode_manager.get_mode()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
async def health():
    try:
        comfy = await comfyui_health()
        return {"ok": True, "comfyui": comfy}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/scene/pipeline")
async def scene_pipeline(scene_data: dict):
    """
    Full pipeline: preprocess -> render -> return.
    """
    mode = mode_manager.get_mode()
    plan = preprocess_scene(scene_data, mode)
    comfy_result = await comfy_bridge.queue_render(plan["render_ready_prompt"])
    plan["comfy_response"] = comfy_result
    return plan

# -----------------------------------------------------
# GUI Support Endpoint
# -----------------------------------------------------
@app.get("/gui/state")
async def gui_state():
    """
    Simple endpoint for GUI to poll status + current mode.
    """
    try:
        comfy = await comfyui_health()
        return {
            "status": "online",
            "mode": mode_manager.get_mode(),
            "comfyui_online": True,
            "comfyui_stats": comfy,
        }
    except Exception:
        return {
            "status": "degraded",
            "mode": mode_manager.get_mode(),
            "comfyui_online": False,
        }

# -----------------------------------------------------
# Entrypoint
# -----------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "comfyvn.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=os.environ.get("UVICORN_RELOAD", "0") == "1",
        log_level="info",
    )
# [ComfyVN: Code Updates Chat + GUI Integration Sync]
