# /app.py
# ComfyVN Server (FastAPI)
# Version: 0.9.0
# Date: 2025-10-10
# [ComfyVN: app.py Gen Chat]

from __future__ import annotations

import os
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
import httpx
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings
from modules.scene_preprocessor import preprocess_scene
#//3. Core Production modification start 10-10-25
from comfyvn.modules.scene_preprocessor import preprocess_scene
from comfyvn.modules.mode_manager import ModeManager

#//3. Core Production
app = FastAPI(title="ComfyVN Server Core", version="1.1")

mode_manager = ModeManager()
comfy_bridge = ComfyUIBridge()

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

@app.post("/scene/plan")
async def scene_plan(scene_data: dict):
    """
    Full scene pipeline:
    1. Preprocess → 2. Generate render prompt → 3. Send to ComfyUI → 4. Return job result
    """
    mode = mode_manager.get_mode()
    plan = preprocess_scene(scene_data, mode)

    comfy_result = comfy_bridge.queue_render(plan["render_ready_prompt"])
    plan["comfy_response"] = comfy_result

    return plan
#//3. Core Production modification end 10-10-25

# ---------------------------------------------
# Settings & Paths
# ---------------------------------------------

class Settings(BaseSettings):
    # Core
    APP_NAME: str = "ComfyVN"
    APP_ENV: str = "dev"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Integrations
    COMFYUI_BASE: str = "http://127.0.0.1:8188"  # e.g., http://localhost:8188
    LMSTUDIO_BASE: str = "http://127.0.0.1:1234/v1"  # OpenAI-compatible
    SILLYTAVERN_WEBHOOK_URL: Optional[str] = None     # e.g., http://localhost:65000/webhook/comfyvn
    RENPY_CLI: Optional[str] = None                   # e.g., /opt/renpy/renpy.sh

    # Project folders
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

# Ensure directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
settings.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------
# Optional Imports (Local Modules)
# ---------------------------------------------

try:
    # from comfyvn.modules.persona_manager import PersonaManager
    # If your module exists, use it. Else, provide a soft fallback.
    from comfyvn.modules.persona_manager import PersonaManager  # type: ignore
except Exception:
    class PersonaManager:
        """Fallback Persona Manager stub"""
        def __init__(self):
            self.persona_enabled = True
            self.group_positions = ["left", "center", "right"]

        def arrange_characters(self, characters: List[Dict[str, Any]]) -> Dict[str, str]:
            layout: Dict[str, str] = {}
            for i, char in enumerate(characters):
                layout[char.get("id", f"char{i}")] = self.group_positions[i % len(self.group_positions)]
            return layout


persona_manager = PersonaManager()  # [ComfyVN: app.py Gen Chat]


# ---------------------------------------------
# FastAPI App
# ---------------------------------------------

app = FastAPI(title=settings.APP_NAME, version="0.9.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------
# HTTPX Client (shared)
# ---------------------------------------------

_client: Optional[httpx.AsyncClient] = None


@app.on_event("startup")
async def _startup() -> None:
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=60.0))
    # lazy health warming (non-blocking)
    asyncio.create_task(_warm_health())


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def _warm_health():
    try:
        await comfyui_health()
    except Exception:
        pass
    try:
        await lmstudio_models()
    except Exception:
        pass


def _get_client() -> httpx.AsyncClient:
    if not _client:
        raise RuntimeError("HTTP client not initialized")
    return _client


# ---------------------------------------------
# Schemas
# ---------------------------------------------

class LLMPlanRequest(BaseModel):
    system_prompt: str = Field(default="You are a VN scene planner. Output concise JSON beats.")
    user_prompt: str
    model: str = Field(default="lmstudio-community/gpt-4o-mini")  # Example alias in LM Studio
    temperature: float = 0.5
    max_tokens: int = 1024


class LLMPlanResponse(BaseModel):
    plan_json: Dict[str, Any]
    raw_text: str


class RenderRequest(BaseModel):
    workflow_file: str = Field(..., description="Relative path under /workflows, .json")
    overrides: Dict[str, Any] = Field(default_factory=dict, description="Node param overrides")
    output_dir: Optional[str] = Field(default=None, description="Relative under /exports")
    queue: bool = True


class RenderResponse(BaseModel):
    queued: bool
    prompt_id: Optional[str] = None
    comfy_response: Optional[Dict[str, Any]] = None
    output_dir: Optional[str] = None


class PersonaLayoutRequest(BaseModel):
    characters: List[Dict[str, Any]]


class PersonaLayoutResponse(BaseModel):
    layout: Dict[str, str]


class SillyTavernPushRequest(BaseModel):
    message: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class RenpyCompileRequest(BaseModel):
    project_dir: str
    script_entry: Optional[str] = None   # e.g., "game/script.rpy"
    args: List[str] = Field(default_factory=list)


# ---------------------------------------------
# Utilities
# ---------------------------------------------

def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read JSON: {e}")  # [ComfyVN: app.py Gen Chat]


def _resolve_under(base: Path, relative: str) -> Path:
    p = (base / relative).resolve()
    if base not in p.parents and p != base:
        raise HTTPException(status_code=400, detail="Path escape detected")
    return p


# ---------------------------------------------
# Health & Config
# ---------------------------------------------

@app.get("/health")
async def health() -> Dict[str, Any]:
    comfy_ok, comfy_err = await _safe(comfyui_health)
    lm_ok, lm_err = await _safe(lmstudio_models)
    return {
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "comfyui": {"ok": comfy_ok, "error": comfy_err},
        "lmstudio": {"ok": lm_ok, "error": lm_err},
        "sillytavern_webhook": bool(settings.SILLYTAVERN_WEBHOOK_URL),
        "renpy_cli": bool(settings.RENPY_CLI),
    }


async def _safe(coro, *args, **kwargs):
    try:
        res = await coro(*args, **kwargs)
        return True, res
    except Exception as e:
        return False, str(e)


@app.get("/config")
def get_config() -> Dict[str, Any]:
    return {
        "COMFYUI_BASE": settings.COMFYUI_BASE,
        "LMSTUDIO_BASE": settings.LMSTUDIO_BASE,
        "SILLYTAVERN_WEBHOOK_URL": settings.SILLYTAVERN_WEBHOOK_URL,
        "RENPY_CLI": settings.RENPY_CLI,
        "WORKFLOWS_DIR": str(settings.WORKFLOWS_DIR),
        "DATA_DIR": str(settings.DATA_DIR),
        "EXPORTS_DIR": str(settings.EXPORTS_DIR),
    }


# ---------------------------------------------
# ComfyUI Helpers
# ---------------------------------------------

async def comfyui_health() -> Dict[str, Any]:
    client = _get_client()
    url = f"{settings.COMFYUI_BASE}/system_stats"
    r = await client.get(url)
    r.raise_for_status()
    return r.json()  # [ComfyVN: app.py Gen Chat]


async def comfyui_queue_prompt(payload: Dict[str, Any]) -> Dict[str, Any]:
    client = _get_client()
    url = f"{settings.COMFYUI_BASE}/prompt"
    r = await client.post(url, json=payload)
    r.raise_for_status()
    return r.json()


async def comfyui_history(prompt_id: str) -> Dict[str, Any]:
    client = _get_client()
    url = f"{settings.COMFYUI_BASE}/history/{prompt_id}"
    r = await client.get(url)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------
# LM Studio (OpenAI-compatible) Helpers
# ---------------------------------------------

async def lmstudio_chat(model: str, messages: List[Dict[str, str]], temperature: float = 0.5, max_tokens: int = 1024) -> str:
    client = _get_client()
    url = f"{settings.LMSTUDIO_BASE}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    r = await client.post(url, json=payload)
    r.raise_for_status()
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        raise HTTPException(status_code=500, detail=f"Unexpected LM Studio response: {data}")  # [ComfyVN: app.py Gen Chat]


async def lmstudio_models() -> Dict[str, Any]:
    client = _get_client()
    url = f"{settings.LMSTUDIO_BASE}/models"
    r = await client.get(url)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------
# SillyTavern Webhook Helper
# ---------------------------------------------

async def sillytavern_push(message: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    if not settings.SILLYTAVERN_WEBHOOK_URL:
        raise HTTPException(status_code=400, detail="SILLYTAVERN_WEBHOOK_URL not configured")
    client = _get_client()
    r = await client.post(settings.SILLYTAVERN_WEBHOOK_URL, json={"message": message, "meta": meta})
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"ok": True, "status_code": r.status_code}


# ---------------------------------------------
# Ren'Py CLI Helper
# ---------------------------------------------

def run_renpy(project_dir: Path, script_entry: Optional[str], extra_args: List[str]) -> Dict[str, Any]:
    if not settings.RENPY_CLI:
        raise HTTPException(status_code=400, detail="RENPY_CLI not configured")

    renpy = Path(settings.RENPY_CLI).resolve()
    if not renpy.exists():
        raise HTTPException(status_code=400, detail=f"Ren'Py CLI not found at {renpy}")

    project_dir = project_dir.resolve()
    if not project_dir.exists():
        raise HTTPException(status_code=400, detail=f"Ren'Py project dir not found: {project_dir}")

    cmd = [str(renpy), str(project_dir)]
    if script_entry:
        cmd += ["compile", script_entry]
    cmd += extra_args

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],  # truncate
            "stderr": proc.stderr[-4000:],
            "cmd": cmd,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ren'Py exec failed: {e}")  # [ComfyVN: app.py Gen Chat]


# ---------------------------------------------
# Endpoints
# ---------------------------------------------

@app.post("/scene/plan", response_model=LLMPlanResponse)
async def scene_plan(req: LLMPlanRequest) -> LLMPlanResponse:
    """
    Use LM Studio to produce a structured scene plan (JSON).
    """
    messages = [
        {"role": "system", "content": req.system_prompt},
        {"role": "user", "content": req.user_prompt},
    ]
    raw = await lmstudio_chat(
        model=req.model,
        messages=messages,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )

    # Attempt to extract JSON plan
    plan_json: Dict[str, Any]
    try:
        # try parse first code fence or raw json
        s = raw.strip()
        if "```" in s:
            s = s.split("```", 2)[1]
            # possible "json\n{...}" then strip first line if non-brace
            if "\n" in s and not s.strip().startswith("{"):
                s = "\n".join(s.splitlines()[1:])
        plan_json = json.loads(s)
    except Exception:
        # Fallback to minimal envelope
        plan_json = {"beats": [], "raw": raw}

    return LLMPlanResponse(plan_json=plan_json, raw_text=raw)


@app.post("/scene/render", response_model=RenderResponse)
async def scene_render(req: RenderRequest) -> RenderResponse:
    """
    Load a ComfyUI workflow JSON, apply overrides, and queue it.
    """
    wf_path = _resolve_under(settings.WORKFLOWS_DIR, req.workflow_file)
    if not wf_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow file not found: {wf_path}")

    payload = _read_json(wf_path)

    # Apply shallow overrides: {node_id: {param: value}}
    for node_id, params in req.overrides.items():
        if node_id in payload.get("nodes", {}):
            payload["nodes"][node_id].update(params)
        else:
            # broad case: some ComfyUI exports have flat dict by id
            if node_id in payload:
                if isinstance(payload[node_id], dict) and isinstance(params, dict):
                    payload[node_id].update(params)
                else:
                    payload[node_id] = params
            else:
                # create if not present
                payload[node_id] = params

    # Optional output dir to help post-processers
    output_dir = settings.EXPORTS_DIR / (req.output_dir or "latest")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload.setdefault("client_id", "comfyvn")
    payload.setdefault("extra_data", {})
    payload["extra_data"]["comfyvn_output_dir"] = str(output_dir)

    if not req.queue:
        return RenderResponse(queued=False, comfy_response=payload, output_dir=str(output_dir))

    comfy_resp = await comfyui_queue_prompt(payload)
    prompt_id = comfy_resp.get("prompt_id") or comfy_resp.get("promptId")

    return RenderResponse(
        queued=True,
        prompt_id=prompt_id,
        comfy_response=comfy_resp,
        output_dir=str(output_dir),
    )


@app.get("/scene/render/history/{prompt_id}")
async def scene_render_history(prompt_id: str) -> Dict[str, Any]:
    return await comfyui_history(prompt_id)


@app.post("/persona/layout", response_model=PersonaLayoutResponse)
async def persona_layout(req: PersonaLayoutRequest) -> PersonaLayoutResponse:
    layout = persona_manager.arrange_characters(req.characters)
    return PersonaLayoutResponse(layout=layout)


@app.post("/sillytavern/push")
async def push_sillytavern(req: SillyTavernPushRequest) -> Dict[str, Any]:
    return await sillytavern_push(req.message, req.meta)


@app.post("/renpy/compile")
def renpy_compile(req: RenpyCompileRequest) -> Dict[str, Any]:
    project_dir = Path(req.project_dir)
    return run_renpy(project_dir, req.script_entry, req.args)


@app.get("/workflows/list")
def list_workflows(suffix: str = Query(".json", description="File suffix filter")) -> List[str]:
    files: List[str] = []
    for p in settings.WORKFLOWS_DIR.rglob(f"*{suffix}"):
        rel = p.relative_to(settings.WORKFLOWS_DIR).as_posix()
        files.append(rel)
    files.sort()
    return files


@app.get("/exports/list")
def list_exports() -> List[str]:
    entries = []
    for p in settings.EXPORTS_DIR.iterdir():
        entries.append(p.name)
    return sorted(entries)


# ---------------------------------------------
# Entrypoint
# ---------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=os.environ.get("UVICORN_RELOAD", "0") == "1",
        log_level="info",
    )
# [ComfyVN: app.py Gen Chat]
