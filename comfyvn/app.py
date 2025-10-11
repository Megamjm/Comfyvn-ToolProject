# comfyvn/app.py
# ⚙️ ComfyVN Server Core – Integration Sync (v2.6-integrated)
# Merge of: [3. Server Core Production Chat v2.4-stsync] + [4. Asset & Sprite System Branch v0.3.3]
# Date: 2025-10-11

from __future__ import annotations
import os, json, asyncio, subprocess, hashlib
from pathlib import Path
from typing import Any, Dict, Optional
import httpx, uvicorn, requests
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
from modules.st_sync_manager import STSyncManager

# 🧍 Asset & Sprite System Modules
from modules.export_manager import ExportManager
from modules.cache_manager import CacheManager
from modules.asset_index import load_index, add_record, query_index
from modules.model_discovery import (
    list_models, verify_integrity, load_community_registry,
    filter_verified_assets, safe_mode_enabled
)
from modules.scene_compositor import compose_scene_png
from modules.workflow_bridge import render_character

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
st_sync = STSyncManager(base_url=os.getenv("SILLYTAVERN_URL", "http://127.0.0.1:8000"))
export_manager = ExportManager()
cache_manager = CacheManager()

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
app = FastAPI(title=settings.APP_NAME, version="2.6-integrated")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# -----------------------------------------------------
# FILE PATHS / GLOBALS
# -----------------------------------------------------
DATA_PATH = "./comfyvn/data"
STYLES_PATH = f"{DATA_PATH}/styles_registry.json"
COMMUNITY_ASSET_PATH = f"{DATA_PATH}/community_assets_registry.json"
LEGAL_FILE_PATH = f"{DATA_PATH}/legal_disclaimer.txt"
COMMUNITY_REGISTRY_URL = "https://raw.githubusercontent.com/Megamjm/ComfyVN-CommunityAssets/main/community_assets_registry.json"
REGISTRY_VERSION_URL = "https://raw.githubusercontent.com/Megamjm/ComfyVN-CommunityAssets/main/registry_version.json"
SAFE_MODE_ENV = "COMFYVN_SAFE_MODE"

# -----------------------------------------------------
# HTTPX CLIENT
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

# -----------------------------------------------------
# UTILITIES
# -----------------------------------------------------
def load_styles():
    try:
        with open(STYLES_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("presets", [])
    except Exception:
        return []

def get_legal_disclaimer():
    try:
        with open(LEGAL_FILE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Legal disclaimer unavailable."

def _pose_hash(cfg: dict) -> str:
    s = json.dumps(cfg.get("pose", {}), sort_keys=True)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# -----------------------------------------------------
# CORE HEALTH / MODE
# -----------------------------------------------------
@app.get("/")
async def root(): return {"status": "ComfyVN Server Online", "mode": mode_manager.get_mode(), "safe_mode": safe_mode_enabled()}

@app.get("/health")
async def health(): return {"ok": True, "version": app.version}

@app.post("/mode/set")
async def set_mode(data: dict):
    try:
        mode_manager.set_mode(data.get("mode"))
        return {"success": True, "mode": mode_manager.get_mode()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# -----------------------------------------------------
# SAFE MODE + LEGAL
# -----------------------------------------------------
@app.get("/safe_mode")
async def safe_get(): return {"safe_mode": safe_mode_enabled()}

@app.post("/safe_mode")
async def safe_set(payload: dict):
    os.environ[SAFE_MODE_ENV] = "1" if payload.get("enabled") else "0"
    return {"safe_mode": safe_mode_enabled()}

@app.get("/legal/disclaimer")
async def legal(): return {"text": get_legal_disclaimer()}

# -----------------------------------------------------
# WORLD MANAGEMENT / ST SYNC
# -----------------------------------------------------
@app.get("/worlds/list")
async def worlds_list(): return {"worlds": list_worlds(), "active": get_active()}

@app.post("/worlds/pull")
async def worlds_pull(payload: dict):
    key = payload.get("world_key", "default")
    ep = payload.get("endpoint")
    return pull_from_sillytavern(ep or os.getenv("SILLYTAVERN_URL","http://127.0.0.1:8000/api/world/export"), key)

@app.post("/worlds/set_active")
async def worlds_set(payload: dict):
    name = payload.get("name")
    if not name: raise HTTPException(status_code=400, detail="Missing 'name'")
    return set_active(name)

# -----------------------------------------------------
# ST SYNC (Direct + Job-Wrapped)
# -----------------------------------------------------
@app.post("/st/sync")
async def st_sync_endpoint(payload: dict):
    a, k = payload.get("asset_type"), payload.get("key")
    if not a or not k: raise HTTPException(status_code=400, detail="Missing asset_type/key")
    suffix = {
        "world": "world/export", "character": "character/export", "lorebook": "lorebook/export",
        "persona": "persona/export", "chat": "chat/export"
    }.get(a)
    if not suffix: raise HTTPException(status_code=400, detail=f"Unsupported {a}")
    return st_sync.sync_asset(a, k, suffix)

@app.post("/st/sync_many")
async def st_sync_many(payload: dict):
    a, keys = payload.get("asset_type"), payload.get("keys", [])
    if not a or not keys: raise HTTPException(status_code=400, detail="Missing asset_type/keys")
    suffix = {
        "world": "world/export", "character": "character/export", "lorebook": "lorebook/export",
        "persona": "persona/export", "chat": "chat/export"
    }.get(a)
    return st_sync.sync_many(a, keys, suffix)

@app.post("/st/query")
async def st_query(payload: dict):
    a, k = payload.get("asset_type"), payload.get("key")
    if not a or not k: raise HTTPException(status_code=400, detail="Missing asset_type/key")
    return st_sync.query_asset(a, k)

@app.post("/st/sync_job")
async def st_sync_job(payload: dict):
    a, k = payload.get("asset_type"), payload.get("key")
    if not a or not k: raise HTTPException(status_code=400, detail="Missing asset_type/key")
    job = job_manager.create("st_sync", payload)
    try:
        job_manager.update(job["id"], status="processing", progress=0.3)
        suffix = {"world": "world/export", "character": "character/export",
                  "lorebook": "lorebook/export", "persona": "persona/export",
                  "chat": "chat/export"}.get(a)
        result = st_sync.sync_asset(a, k, suffix)
        job_manager.complete(job["id"], result)
        return {"job": job_manager.get(job["id"])}
    except Exception as e:
        job_manager.fail(job["id"], str(e)); raise HTTPException(status_code=500, detail=str(e))

@app.post("/st/sync_many_job")
async def st_sync_many_job(payload: dict):
    a, keys = payload.get("asset_type"), payload.get("keys", [])
    job = job_manager.create("st_sync_many", payload)
    try:
        total, results = len(keys), {}
        for i, k in enumerate(keys, start=1):
            job_manager.update(job["id"], status=f"processing:{i}/{total}", progress=round(i/total, 2))
            results[k] = st_sync.sync_asset(a, k, "character/export")
        job_manager.complete(job["id"], {"count": total, "results": results})
        return {"job": job_manager.get(job["id"])}
    except Exception as e:
        job_manager.fail(job["id"], str(e)); raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------
# ASSET & SPRITE SYSTEM – Styles, Models, Community, Rendering
# -----------------------------------------------------
@app.get("/styles/list")
async def styles_list(): return {"styles": load_styles(), "legal": get_legal_disclaimer()}

@app.get("/models/list")
async def models_list():
    models = list_models()
    return {"summary": {k: len(v) for k, v in models.items()}, "models": models, "legal": get_legal_disclaimer()}

@app.get("/assets/community")
async def assets_community():
    data = load_community_registry()
    return {"safe_mode": safe_mode_enabled(), "assets": filter_verified_assets(data), "legal": get_legal_disclaimer()}

@app.post("/assets/register")
async def assets_register(payload: dict):
    if safe_mode_enabled(): raise HTTPException(status_code=403, detail="Safe Mode active")
    try:
        data = load_community_registry()
        data.setdefault("unverified_user", []).append(payload)
        with open(COMMUNITY_ASSET_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return {"ok": True, "added": payload.get("name")}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/assets/update_registry")
async def assets_update_registry():
    r = requests.get(COMMUNITY_REGISTRY_URL, timeout=10)
    r.raise_for_status()
    with open(COMMUNITY_ASSET_PATH, "w", encoding="utf-8") as f:
        json.dump(r.json(), f, indent=2)
    return {"ok": True, "src": COMMUNITY_REGISTRY_URL}

@app.post("/render/char")
async def render_character_api(cfg: dict):
    character = cfg.get("character") or {}
    if not character: raise HTTPException(status_code=400, detail="Missing character")
    style_id, control_stack, seed = cfg.get("style_id"), cfg.get("control_stack", []), int(cfg.get("seed", 123))
    pose_hash = _pose_hash(cfg)
    key = cache_manager.make_cache_key(style_id or "default", control_stack, {}, pose_hash, seed)
    cached = cache_manager.load_sprite(key)
    if cached and os.path.exists(cached.get("png_path","")):
        return {"cached": True, "path": cached["png_path"]}
    png_bytes, meta = render_character(cfg)
    export = export_manager.export_character_dump(character, style_id, control_stack, sprite_png_bytes=png_bytes)
    png_path = os.path.join(export, f"{character.get('id')}.png")
    cache_manager.cache_sprite(key, {"export_path": export, "png_path": png_path})
    return {"cached": False, "export_path": export}

@app.post("/render/scene")
async def render_scene(cfg: dict):
    scene_id = cfg.get("scene_id", "scene")
    layers, out_name = cfg.get("layers", []), cfg.get("out_name", f"{scene_id}.png")
    if not layers: raise HTTPException(status_code=400, detail="Missing layers[]")
    out_dir = f"./exports/assets/{scene_id}"; os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    compose_scene_png(layers, out_path)
    add_record({"type": "scene_composite", "scene_id": scene_id, "export_path": out_path, "layers": layers})
    return {"ok": True, "path": out_path}

# -----------------------------------------------------
# ASSET INDEX
# -----------------------------------------------------
@app.get("/assets/index")
async def asset_index(): i = load_index(); return {"count": len(i.get("items",[])), "items": i.get("items",[])}

@app.post("/assets/index/query")
async def asset_index_query(payload: dict): r = query_index(**payload); return {"count": len(r), "items": r}

# -----------------------------------------------------
# AUDIO / LORA / PLAYGROUND / NPC / GROUP
# -----------------------------------------------------
@app.get("/audio/get")
async def audio_get(): return audio_manager.get()

@app.post("/audio/toggle")
async def audio_toggle(payload: dict):
    k = payload.get("key"); s = bool(payload.get("state", True))
    if not k: raise HTTPException(status_code=400, detail="Missing key")
    return audio_manager.toggle(k, s)

@app.get("/lora/search")
async def lora_search(query: str): return {"results": lora_manager.search(query)}

@app.post("/lora/register")
async def lora_register(payload: dict):
    n = payload.get("name"); m = payload.get("meta", {})
    if not n: raise HTTPException(status_code=400, detail="Missing name")
    return lora_manager.register(n, m)

@app.get("/lora/meta/{name}")
async def lora_meta(name: str): return lora_manager.load_meta(name)

@app.post("/playground/apply")
async def playground_apply(payload: dict):
    sid, prompt = payload.get("scene_id"), payload.get("prompt")
    if not sid or not prompt: raise HTTPException(status_code=400, detail="Missing fields")
    return playground.apply_prompt(sid, prompt)

@app.get("/playground/history/{scene_id}")
async def playground_history(scene_id: str): return {"scene_id": scene_id, "history": playground.get_history(scene_id)}

@app.post("/group/arrange")
async def group_arrange(payload: dict):
    chars = payload.get("characters", [])
    if not isinstance(chars, list) or not chars:
        raise HTTPException(status_code=400, detail="Provide characters[]")
    return {"layout": persona.arrange_characters(chars)}

@app.post("/npc/generate")
async def npc_generate(payload: dict):
    return {"npcs": npc.generate(payload.get("scene_context", {}))}

# -----------------------------------------------------
# JOB MGMT + STREAMING
# -----------------------------------------------------
@app.get("/jobs")
async def jobs_list(): return {"jobs": job_manager.list()}

@app.get("/jobs/poll")
async def jobs_poll(): return job_manager.poll()

@app.get("/jobs/{jid}")
async def jobs_get(jid: str): return job_manager.get(jid)

@app.get("/jobs/history")
async def jobs_hist():
    logs = "./logs/jobs"
    if not os.path.exists(logs): return {"history":[]}
    out=[]
    for f in sorted(os.listdir(logs))[-10:]:
        with open(os.path.join(logs,f)) as fp: out.append(json.load(fp))
    return {"history": out}

@app.get("/sse/jobs")
async def sse_jobs(request: Request):
    async def gen():
        q = await event_bus.subscribe()
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
                if await request.is_disconnected(): break
        finally: await event_bus.unsubscribe(q)
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.websocket("/ws/jobs")
async def ws_jobs(ws: WebSocket):
    await ws.accept()
    q = await event_bus.subscribe()
    try:
        await ws.send_text(json.dumps({"type":"hello","jobs":job_manager.list()}))
        while True: await ws.send_text(await q.get())
    except WebSocketDisconnect: pass
    finally: await event_bus.unsubscribe(q)

# -----------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "comfyvn.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=os.environ.get("UVICORN_RELOAD","0")=="1",
        log_level="info",
    )
    # Example: UVICORN_RELOAD=1 python comfyvn/app.py