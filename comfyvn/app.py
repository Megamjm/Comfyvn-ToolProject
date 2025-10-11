# comfyvn/app.py
# ⚙️ ComfyVN Server Core – Integration Sync + ST Generic Sync (Patch B)
# Base: v2.3-sync  |  Date: 2025-10-11
# [⚙️ 3. Server Core Production Chat]

from __future__ import annotations
import os, json, asyncio, subprocess
from pathlib import Path
from typing import Any, Dict, Optional
import httpx, uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings

# -----------------------------------------------------
# MODULE IMPORTS
# -----------------------------------------------------
from modules.world_loader import list_worlds, pull_from_sillytavern, set_active, get_active
from modules.audio_manager import AudioManager
from modules.lora_manager import LoRAManager
from modules.playground_manager import PlaygroundManager
from modules.persona_manager import PersonaManager
from modules.npc_manager import NPCManager
from modules.scene_preprocessor import preprocess_scene
from modules.mode_manager import ModeManager
from modules.event_bus import EventBus
from modules.job_manager import JobManager
from modules.st_sync_manager import STSyncManager  # 🆕 NEW MODULE IMPORT

# -----------------------------------------------------
# INITIALIZATION
# -----------------------------------------------------
audio_manager = AudioManager()
lora_manager = LoRAManager()
playground = PlaygroundManager()
persona = PersonaManager()
npc = NPCManager()
mode_manager = ModeManager()
event_bus = EventBus()
job_manager = JobManager(event_bus=event_bus)

# NEW: ST SYNC MANAGER INITIALIZATION
st_sync = STSyncManager(base_url=os.getenv("SILLYTAVERN_URL", "http://127.0.0.1:8000"))

# -----------------------------------------------------
# SETTINGS
# -----------------------------------------------------
class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", case_sensitive=True)
    APP_NAME: str = "ComfyVN Server Core"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    COMFYUI_BASE: str = "http://127.0.0.1:8188"
    PROJECT_ROOT: Path = Path(__file__).parent.resolve()
    DATA_DIR: Path = Field(default_factory=lambda: Path("./data").resolve())
    EXPORTS_DIR: Path = Field(default_factory=lambda: Path("./exports").resolve())

    @field_validator("DATA_DIR", "EXPORTS_DIR", mode="before")
    def _ensure_path(cls, v): return Path(v).resolve()

settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------
# FASTAPI APP
# -----------------------------------------------------
app = FastAPI(title=settings.APP_NAME, version="2.4-stsync")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# -----------------------------------------------------
# HTTPX CLIENT MGMT
# -----------------------------------------------------
_client: Optional[httpx.AsyncClient] = None

@app.on_event("startup")
async def _startup():
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=60.0))

@app.on_event("shutdown")
async def _shutdown():
    global _client
    if _client: await _client.aclose(); _client = None

def _get_client() -> httpx.AsyncClient:
    if not _client:
        raise RuntimeError("HTTP client not initialized")
    return _client

# -----------------------------------------------------
# CORE HEALTH + MODE
# -----------------------------------------------------
@app.get("/")
async def root():
    return {"status": "ComfyVN Server Online", "mode": mode_manager.get_mode()}

@app.get("/health")
async def health():
    return {"ok": True, "version": app.version}

@app.get("/version")
async def version():
    return {"version": app.version}

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

# -----------------------------------------------------
# WORLD MANAGEMENT (Pull + Compare)
# -----------------------------------------------------
@app.get("/worlds/list")
async def worlds_list():
    return {"worlds": list_worlds(), "active": get_active()}

@app.post("/worlds/pull")
async def worlds_pull(payload: dict):
    key = payload.get("world_key", "default")
    ep = payload.get("endpoint")
    result = pull_from_sillytavern(ep or os.getenv("SILLYTAVERN_URL","http://127.0.0.1:8000/api/world/export"), key)
    return result

@app.post("/worlds/set_active")
async def worlds_set_active(payload: dict):
    name = payload.get("name")
    if not name: raise HTTPException(status_code=400, detail="Missing 'name'")
    return set_active(name)

# -----------------------------------------------------
# ST GENERIC SYNC (SillyTavern)
# -----------------------------------------------------
@app.post("/st/sync")
async def st_sync_endpoint(payload: dict):
    """
    Sync a single ST asset: { "asset_type": "world"/"character"/"lorebook", "key": "name" }
    """
    asset_type = payload.get("asset_type")
    key = payload.get("key")
    if not asset_type or not key:
        raise HTTPException(status_code=400, detail="Missing 'asset_type' or 'key'")

    suffix_map = {
        "world": "world/export",
        "character": "character/export",
        "lorebook": "lorebook/export",
        "persona": "persona/export",
        "chat": "chat/export"
    }
    suffix = suffix_map.get(asset_type)
    if not suffix:
        raise HTTPException(status_code=400, detail=f"Unsupported asset_type '{asset_type}'")

    result = st_sync.sync_asset(asset_type, key, suffix)
    return result

@app.post("/st/sync_many")
async def st_sync_many(payload: dict):
    asset_type = payload.get("asset_type")
    keys = payload.get("keys", [])
    if not asset_type or not keys:
        raise HTTPException(status_code=400, detail="Missing 'asset_type' or 'keys'")
    suffix_map = {
        "world": "world/export",
        "character": "character/export",
        "lorebook": "lorebook/export",
        "persona": "persona/export",
        "chat": "chat/export"
    }
    suffix = suffix_map.get(asset_type)
    if not suffix:
        raise HTTPException(status_code=400, detail=f"Unsupported {asset_type}")
    return st_sync.sync_many(asset_type, keys, suffix)

@app.post("/st/query")
async def st_query(payload: dict):
    asset_type = payload.get("asset_type")
    key = payload.get("key")
    if not asset_type or not key:
        raise HTTPException(status_code=400, detail="Missing 'asset_type' or 'key'")
    return st_sync.query_asset(asset_type, key)

# -----------------------------------------------------
# AUDIO CONTROL
# -----------------------------------------------------
@app.get("/audio/get")
async def audio_get(): return audio_manager.get()

@app.post("/audio/toggle")
async def audio_toggle(payload: dict):
    key = payload.get("key"); state = bool(payload.get("state", True))
    if not key: raise HTTPException(status_code=400, detail="Missing 'key'")
    return audio_manager.toggle(key, state)

# -----------------------------------------------------
# LORA MANAGEMENT
# -----------------------------------------------------
@app.get("/lora/search")
async def lora_search(query: str): return {"query": query, "results": lora_manager.search(query)}

@app.post("/lora/register")
async def lora_register(payload: dict):
    name = payload.get("name"); meta = payload.get("meta", {})
    if not name: raise HTTPException(status_code=400, detail="Missing 'name'")
    return lora_manager.register(name, meta)

@app.get("/lora/meta/{name}")
async def lora_meta(name: str): return lora_manager.load_meta(name)

# -----------------------------------------------------
# PLAYGROUND – SCENE MUTATION
# -----------------------------------------------------
@app.post("/playground/apply")
async def playground_apply(payload: dict):
    sid = payload.get("scene_id"); prompt = payload.get("prompt")
    if not sid or not prompt:
        raise HTTPException(status_code=400, detail="Missing 'scene_id' or 'prompt'")
    return playground.apply_prompt(sid, prompt)

@app.get("/playground/history/{scene_id}")
async def playground_history(scene_id: str):
    return {"scene_id": scene_id, "history": playground.get_history(scene_id)}

# -----------------------------------------------------
# GROUP + NPC
# -----------------------------------------------------
@app.post("/group/arrange")
async def group_arrange(payload: dict):
    chars = payload.get("characters", [])
    if not isinstance(chars, list) or not chars:
        raise HTTPException(status_code=400, detail="Provide 'characters' list")
    return {"layout": persona.arrange_characters(chars)}

@app.post("/npc/generate")
async def npc_generate(payload: dict):
    ctx = payload.get("scene_context", {})
    return {"npcs": npc.generate(ctx)}

# -----------------------------------------------------
# JOB MANAGEMENT (poll + history + WS)
# -----------------------------------------------------
@app.get("/jobs")
async def jobs_list(): return {"jobs": job_manager.list()}

@app.get("/jobs/poll")
async def jobs_poll(): return job_manager.poll()

@app.get("/jobs/{job_id}")
async def jobs_get(job_id: str): return job_manager.get(job_id)

@app.get("/jobs/history")
async def jobs_history():
    import os, json
    logs_path = "./logs/jobs"
    if not os.path.exists(logs_path): return {"history": []}
    entries = []
    for f in sorted(os.listdir(logs_path))[-10:]:
        with open(os.path.join(logs_path, f), "r", encoding="utf-8") as fp:
            entries.append(json.load(fp))
    return {"history": entries}

# -----------------------------------------------------
# SSE STREAM (optional GUI fallback)
# -----------------------------------------------------
@app.get("/sse/jobs")
async def sse_jobs(request: Request):
    async def event_generator():
        q = await event_bus.subscribe()
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
                if await request.is_disconnected(): break
        finally:
            await event_bus.unsubscribe(q)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# -----------------------------------------------------
# WEBSOCKET – JOB EVENTS
# -----------------------------------------------------
@app.websocket("/ws/jobs")
async def ws_jobs(websocket: WebSocket):
    await websocket.accept()
    queue = await event_bus.subscribe()
    try:
        snapshot = {"type": "hello", "jobs": job_manager.list()}
        await websocket.send_text(json.dumps(snapshot))
        while True:
            msg = await queue.get()
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        pass
    finally:
        await event_bus.unsubscribe(queue)

# -----------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "comfyvn.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=os.environ.get("UVICORN_RELOAD", "0") == "1",
        log_level="info",
    )
# [⚙️ 3. Server Core Production Chat]
