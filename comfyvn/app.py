# comfyvn/app.py
# ⚙️ ComfyVN Server Core – Integration Sync (v2.6.2-core-align)
# Merge of: [3. Server Core Production Chat v2.4-stsync] + [4. Asset & Sprite System Branch v0.3.3]
# + GUI v0.4-dev compatibility endpoints (status/metrics, scene alias, jobs control)
# Date: 2025-10-11
# [⚙️ 3. Server Core Production Chat]  # (GUI Code Production Chat)

from __future__ import annotations
import os, json, asyncio, subprocess, hashlib, psutil, time
from pathlib import Path
from typing import Any, Dict, Optional, List
import httpx, uvicorn, requests
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# -----------------------------------------------------
# CORE SETTINGS & MODULE IMPORTS (Aligned)
# -----------------------------------------------------
from comfyvn.core.settings_manager import settings_manager, settings
from comfyvn.core.event_bus import EventBus
from comfyvn.core.job_manager import JobManager
from comfyvn.core.mode_manager import ModeManager

from comfyvn.core.world_loader import list_worlds, pull_from_sillytavern, set_active, get_active
from comfyvn.core.st_sync_manager import STSyncManager

from comfyvn.assets.audio_manager import AudioManager
from comfyvn.assets.lora_manager import LoRAManager
from comfyvn.assets.playground_manager import PlaygroundManager
from comfyvn.assets.persona_manager import PersonaManager
from comfyvn.assets.npc_manager import NPCManager

from comfyvn.core.scene_preprocessor import preprocess_scene
from comfyvn.core.scene_compositor import compose_scene_png
from comfyvn.core.workflow_bridge import render_character

# Asset/Sprite System (kept under assets namespace)
from comfyvn.assets.export_manager import ExportManager
from comfyvn.assets.cache_manager import CacheManager
from comfyvn.assets.asset_index import load_index, add_record, query_index
from comfyvn.assets.model_discovery import (
    list_models, verify_integrity, load_community_registry,
    filter_verified_assets, safe_mode_enabled
)

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
# FASTAPI APP
# -----------------------------------------------------
app = FastAPI(title=settings.APP_NAME, version="2.6.2-core-align")
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
    if _client:
        await _client.aclose()
        _client = None

def _get_client() -> httpx.AsyncClient:
    if not _client:
        raise RuntimeError("HTTP client not initialized")
    return _client

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

def _gpu_details() -> List[dict]:
    """Lightweight GPU probe via nvidia-smi; safe fallback."""
    gpus = []
    try:
        out = subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
        ], stderr=subprocess.DEVNULL).decode().strip()
        for line in out.splitlines():
            idx, name, util, mem_used, mem_total, temp = [x.strip() for x in line.split(",")]
            gpus.append({
                "id": int(idx),
                "name": name,
                "utilization": int(util),
                "mem_used": int(mem_used),
                "mem_total": int(mem_total),
                "temp_c": int(temp),
            })
    except Exception:
        pass
    return gpus

# -----------------------------------------------------
# CORE HEALTH / MODE
# -----------------------------------------------------
@app.get("/")
async def root():
    return {
        "status": "ComfyVN Server Online",
        "mode": mode_manager.get_mode(),
        "safe_mode": safe_mode_enabled(),
        "version": app.version,
    }

# ✅ NEW: GUI compatibility
@app.get("/status")
async def status_simple():
    return {
        "status": "online",
        "mode": mode_manager.get_mode(),
        "version": app.version,
    }

# ✅ NEW: GUI/SystemMonitor compatibility
@app.get("/system/metrics")
async def system_metrics():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    gpus = _gpu_details()
    gpu_percent = gpus[0]["utilization"] if gpus else 0
    return {
        "cpu_percent": cpu,
        "ram_percent": ram,
        "gpu_percent": gpu_percent,
        "gpus": gpus,
    }

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
async def set_mode_api(data: dict):
    try:
        mode_manager.set_mode(data.get("mode"))
        return {"success": True, "mode": mode_manager.get_mode()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# -----------------------------------------------------
# SAFE MODE + LEGAL
# -----------------------------------------------------
@app.get("/safe_mode")
async def safe_get():
    return {"safe_mode": safe_mode_enabled()}

@app.post("/safe_mode")
async def safe_set(payload: dict):
    os.environ[SAFE_MODE_ENV] = "1" if payload.get("enabled") else "0"
    return {"safe_mode": safe_mode_enabled()}

@app.get("/legal/disclaimer")
async def legal():
    return {"text": get_legal_disclaimer()}

# -----------------------------------------------------
# WORLD MANAGEMENT / ST SYNC (Worlds)
# -----------------------------------------------------
@app.get("/worlds/list")
async def worlds_list():
    return {"worlds": list_worlds(), "active": get_active()}

# ✅ NEW: GUI/SystemMonitor compatibility
@app.get("/world/status")
async def world_status():
    return {"status": "online", "active": get_active()}

@app.post("/worlds/pull")
async def worlds_pull(payload: dict):
    key = payload.get("world_key", "default")
    ep = payload.get("endpoint")
    return pull_from_sillytavern(ep or os.getenv("SILLYTAVERN_URL","http://127.0.0.1:8000/api/world/export"), key)

@app.post("/worlds/set_active")
async def worlds_set(payload: dict):
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Missing 'name'")
    return set_active(name)

# -----------------------------------------------------
# ST SYNC (Direct + Job-Wrapped)
# -----------------------------------------------------
_SUFFIX_MAP = {
    "world": "world/export",
    "character": "character/export",
    "lorebook": "lorebook/export",
    "persona": "persona/export",
    "chat": "chat/export",
}

@app.post("/st/sync")
async def st_sync_endpoint(payload: dict):
    a, k = payload.get("asset_type"), payload.get("key")
    if not a or not k:
        raise HTTPException(status_code=400, detail="Missing 'asset_type' or 'key'")
    suffix = _SUFFIX_MAP.get(a)
    if not suffix:
        raise HTTPException(status_code=400, detail=f"Unsupported asset_type '{a}'")
    return st_sync.sync_asset(a, k, suffix)

@app.post("/st/sync_many")
async def st_sync_many(payload: dict):
    a, keys = payload.get("asset_type"), payload.get("keys", [])
    if not a or not keys:
        raise HTTPException(status_code=400, detail="Missing 'asset_type' or 'keys'")
    suffix = _SUFFIX_MAP.get(a)
    if not suffix:
        raise HTTPException(status_code=400, detail=f"Unsupported asset_type '{a}'")
    return st_sync.sync_many(a, keys, suffix)

@app.post("/st/query")
async def st_query(payload: dict):
    a, k = payload.get("asset_type"), payload.get("key")
    if not a or not k:
        raise HTTPException(status_code=400, detail="Missing 'asset_type' or 'key'")
    return st_sync.query_asset(a, k)

@app.post("/st/sync_job")
async def st_sync_job(payload: dict):
    a, k = payload.get("asset_type"), payload.get("key")
    if not a or not k:
        raise HTTPException(status_code=400, detail="Missing 'asset_type' or 'key'")
    job = job_manager.create("st_sync", payload)
    try:
        job_manager.update(job["id"], status="processing", progress=0.3)
        suffix = _SUFFIX_MAP.get(a)
        if not suffix:
            raise HTTPException(status_code=400, detail=f"Unsupported asset_type '{a}'")
        result = st_sync.sync_asset(a, k, suffix)
        job_manager.complete(job["id"], result)
        return {"job": job_manager.get(job["id"])}
    except HTTPException as e:
        job_manager.fail(job["id"], f"HTTP {e.status_code}: {e.detail}")
        raise
    except Exception as e:
        job_manager.fail(job["id"], str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/st/sync_many_job")
async def st_sync_many_job(payload: dict):
    a, keys = payload.get("asset_type"), payload.get("keys", [])
    if not a or not keys:
        raise HTTPException(status_code=400, detail="Missing 'asset_type' or 'keys'")
    job = job_manager.create("st_sync_many", payload)
    try:
        suffix = _SUFFIX_MAP.get(a)
        if not suffix:
            raise HTTPException(status_code=400, detail=f"Unsupported asset_type '{a}'")
        total, results = len(keys), {}
        for i, k in enumerate(keys, start=1):
            job_manager.update(job["id"], status=f"processing:{i}/{total}", progress=round(0.05 + 0.9 * (i - 1) / max(1, total), 3))
            results[k] = st_sync.sync_asset(a, k, suffix)
        job_manager.update(job["id"], progress=0.98)
        job_manager.complete(job["id"], {"asset_type": a, "count": total, "results": results})
        return {"job": job_manager.get(job["id"])}
    except HTTPException as e:
        job_manager.fail(job["id"], f"HTTP {e.status_code}: {e.detail}")
        raise
    except Exception as e:
        job_manager.fail(job["id"], str(e))
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------
# ASSET & SPRITE SYSTEM – Styles, Models, Community, Rendering
# -----------------------------------------------------
@app.get("/styles/list")
async def styles_list():
    return {"styles": load_styles(), "legal": get_legal_disclaimer()}

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
    if safe_mode_enabled():
        raise HTTPException(status_code=403, detail="Safe Mode active")
    try:
        data = load_community_registry()
        data.setdefault("unverified_user", []).append(payload)
        with open(COMMUNITY_ASSET_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return {"ok": True, "added": payload.get("name")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    if not character:
        raise HTTPException(status_code=400, detail="Missing character")
    style_id = cfg.get("style_id")
    control_stack = cfg.get("control_stack", [])
    seed = int(cfg.get("seed", 123))
    pose_hash = _pose_hash(cfg)
    key = cache_manager.make_cache_key(style_id or "default", control_stack, {}, pose_hash, seed)
    cached = cache_manager.load_sprite(key)
    if cached and os.path.exists(cached.get("png_path", "")):
        return {"cached": True, "path": cached["png_path"]}
    png_bytes, meta = render_character(cfg)
    export = export_manager.export_character_dump(character, style_id, control_stack, sprite_png_bytes=png_bytes)
    png_path = os.path.join(export, f"{character.get('id')}.png")
    cache_manager.cache_sprite(key, {"export_path": export, "png_path": png_path})
    return {"cached": False, "export_path": export, "path": png_path}

# Primary scene compose
@app.post("/render/scene")
async def render_scene(cfg: dict):
    scene_id = cfg.get("scene_id", "scene")
    layers = cfg.get("layers", [])
    out_name = cfg.get("out_name", f"{scene_id}.png")
    if not layers:
        raise HTTPException(status_code=400, detail="Missing layers[]")
    out_dir = f"./exports/assets/{scene_id}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    compose_scene_png(layers, out_path)
    add_record({"type": "scene_composite", "scene_id": scene_id, "export_path": out_path, "layers": layers})
    return {"ok": True, "path": out_path}

# ✅ NEW: GUI compatibility alias for /scene/render
@app.post("/scene/render")
async def scene_render_alias(cfg: dict):
    """
    Accepts either:
      - direct layers[] like /render/scene
      - high-level scene (text/characters/background) processed via preprocess_scene
    """
    layers = cfg.get("layers")
    if not layers:
        try:
            processed = preprocess_scene(cfg)  # expected to produce a dict with 'layers'
            layers = processed.get("layers", [])
        except Exception:
            layers = []
    if not layers:
        raise HTTPException(status_code=400, detail="Provide layers[] or a valid scene description.")
    return await render_scene({"scene_id": cfg.get("scene_id", "scene"), "layers": layers, "out_name": cfg.get("out_name")})

# -----------------------------------------------------
# ASSET INDEX
# -----------------------------------------------------
@app.get("/assets/index")
async def asset_index():
    i = load_index()
    return {"count": len(i.get("items", [])), "items": i.get("items", [])}

@app.post("/assets/index/query")
async def asset_index_query(payload: dict):
    r = query_index(**payload)
    return {"count": len(r), "items": r}

# -----------------------------------------------------
# AUDIO / LORA / PLAYGROUND / NPC / GROUP
# -----------------------------------------------------
@app.get("/audio/get")
async def audio_get():
    return audio_manager.get()

@app.post("/audio/toggle")
async def audio_toggle(payload: dict):
    k = payload.get("key")
    s = bool(payload.get("state", True))
    if not k:
        raise HTTPException(status_code=400, detail="Missing key")
    return audio_manager.toggle(k, s)

@app.get("/lora/search")
async def lora_search(query: str):
    return {"results": lora_manager.search(query)}

@app.post("/lora/register")
async def lora_register(payload: dict):
    n = payload.get("name")
    m = payload.get("meta", {})
    if not n:
        raise HTTPException(status_code=400, detail="Missing name")
    return lora_manager.register(n, m)

@app.get("/lora/meta/{name}")
async def lora_meta(name: str):
    return lora_manager.load_meta(name)

@app.post("/playground/apply")
async def playground_apply(payload: dict):
    sid, prompt = payload.get("scene_id"), payload.get("prompt")
    if not sid or not prompt:
        raise HTTPException(status_code=400, detail="Missing fields")
    return playground.apply_prompt(sid, prompt)

@app.get("/playground/history/{scene_id}")
async def playground_history(scene_id: str):
    return {"scene_id": scene_id, "history": playground.get_history(scene_id)}

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
async def jobs_list():
    return {"jobs": job_manager.list()}

@app.get("/jobs/poll")
async def jobs_poll():
    return job_manager.poll()

@app.get("/jobs/{jid}")
async def jobs_get(jid: str):
    return job_manager.get(jid)

# ✅ NEW: controls expected by AdvancedTaskManagerDock
@app.post("/jobs/kill")
async def jobs_kill(payload: dict):
    jid = payload.get("job_id")
    if not jid:
        raise HTTPException(status_code=400, detail="Missing job_id")
    try:
        # Prefer explicit API if available
        if hasattr(job_manager, "kill"):
            job_manager.kill(jid)
        else:
            job_manager.update(jid, status="cancelled", progress=1.0)
            job_manager.complete(jid, {"cancelled": True})
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jobs/pause")
async def jobs_pause(payload: dict):
    jid = payload.get("job_id")
    if not jid:
        raise HTTPException(status_code=400, detail="Missing job_id")
    try:
        if hasattr(job_manager, "pause"):
            job_manager.pause(jid)
        else:
            job_manager.update(jid, status="paused")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jobs/resume")
async def jobs_resume(payload: dict):
    jid = payload.get("job_id")
    if not jid:
        raise HTTPException(status_code=400, detail="Missing job_id")
    try:
        if hasattr(job_manager, "resume"):
            job_manager.resume(jid)
        else:
            job_manager.update(jid, status="processing")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jobs/reallocate")
async def jobs_reallocate(payload: dict):
    jid = payload.get("job_id")
    target = (payload.get("target") or "").lower()
    if not jid or target not in ("cpu", "gpu"):
        raise HTTPException(status_code=400, detail="Provide job_id and target ∈ {cpu,gpu}")
    try:
        job = job_manager.get(jid)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job.setdefault("meta", {})["device"] = target
        job["device"] = target
        job_manager.update(jid, status="processing", progress=job.get("progress", 0.0))
        # broadcast change
        await event_bus.publish(json.dumps({"type": "job_update", "job": job_manager.get(jid)}))
        return {"ok": True, "job": job_manager.get(jid)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jobs/history")
async def jobs_hist():
    logs = "./logs/jobs"
    if not os.path.exists(logs):
        return {"history": []}
    out = []
    for f in sorted(os.listdir(logs))[-10:]:
        with open(os.path.join(logs, f), "r", encoding="utf-8") as fp:
            out.append(json.load(fp))
    return {"history": out}

@app.get("/sse/jobs")
async def sse_jobs(request: Request):
    async def gen():
        q = await event_bus.subscribe()
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
                if await request.is_disconnected():
                    break
        finally:
            await event_bus.unsubscribe(q)
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.websocket("/ws/jobs")
async def ws_jobs(ws: WebSocket):
    await ws.accept()
    q = await event_bus.subscribe()
    try:
        await ws.send_text(json.dumps({"type": "hello", "jobs": job_manager.list()}))
        while True:
            msg = await q.get()
            await ws.send_text(msg)
    except WebSocketDisconnect:
        pass
    finally:
        await event_bus.unsubscribe(q)

# -----------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "comfyvn.app:comfyvn.app",
        host=settings.HOST,
        port=settings.PORT,
        reload=os.environ.get("UVICORN_RELOAD", "0") == "1",
        log_level="info",
    )
# [⚙️ 3. Server Core Production Chat]