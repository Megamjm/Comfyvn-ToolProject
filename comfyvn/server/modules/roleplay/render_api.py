# comfyvn/server/modules/roleplay/render_api.py
# 🧬 Roleplay LoRA Render API — Phase 3.9
# [ComfyVN_Architect | Roleplay Import & Collaboration Chat]

from __future__ import annotations
import os, json, datetime, asyncio, httpx
from typing import Dict, Any, List
from fastapi import APIRouter, Body

router = APIRouter(prefix="/roleplay", tags=["Roleplay Import"])

RENDER_DIR = "./data/roleplay/renders"
os.makedirs(RENDER_DIR, exist_ok=True)


async def _render_single(
    line: Dict[str, str], scene_id: str, model: str, endpoint: str
):
    prompt = f"{line.get('speaker','unknown')} ({line.get('emotion','neutral')}): {line.get('text','')}"
    render_payload = {"prompt": prompt, "model": model}
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0)) as c:
        try:
            r = await c.post(f"{endpoint.rstrip('/')}/render", json=render_payload)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return {"speaker": line.get("speaker"), "error": str(e)}
    fname = f"{scene_id}_{line.get('speaker','unknown')}_{datetime.datetime.now().strftime('%H%M%S')}.json"
    out_path = os.path.join(RENDER_DIR, fname)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"prompt": prompt, "response": data}, f, indent=2)
    return {"speaker": line.get("speaker"), "status": "ok"}


@router.post("/render_scene")
async def render_scene(payload: Dict = Body(...)):
    """
    Queue render for all scene lines.
    {
        "scene_id": "rp_1234",
        "lines": [...],
        "model": "anime-lora",
        "endpoint": "http://127.0.0.1:8188"
    }
    """
    scene_id = payload.get("scene_id", "adhoc")
    lines: List[Dict] = payload.get("lines", [])
    model = payload.get("model", "base")
    endpoint = payload.get("endpoint", "http://127.0.0.1:8188")

    if not lines:
        return {"error": "no lines provided"}

    results = []
    for line in lines:
        res = await _render_single(line, scene_id, model, endpoint)
        results.append(res)

    log_path = os.path.join(
        RENDER_DIR,
        f"{scene_id}_batch_{datetime.datetime.now().strftime('%H%M%S')}.json",
    )
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return {"status": "ok", "rendered": len(results), "log": log_path}
