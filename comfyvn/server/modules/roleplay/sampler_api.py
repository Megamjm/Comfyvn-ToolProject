# comfyvn/server/modules/roleplay/sampler_api.py
# 🤝 Roleplay LLM Sampler API — Phase 3.5
# [Roleplay Import & Collaboration Chat | ComfyVN_Architect]

from __future__ import annotations
import os, json, datetime
from typing import List, Dict, Optional
import httpx
from fastapi import APIRouter, Body

router = APIRouter(prefix="/roleplay", tags=["Roleplay Import"])

CONVERTED_DIR = "./data/roleplay/converted"
PREVIEW_DIR = "./data/roleplay/preview"
META_DIR = "./data/roleplay/metadata"
os.makedirs(PREVIEW_DIR, exist_ok=True)
os.makedirs(META_DIR, exist_ok=True)


def _load_scene(scene_id: str) -> Dict:
    path = os.path.join(CONVERTED_DIR, f"{scene_id}.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_preview(scene_id: str, payload: Dict) -> str:
    out = os.path.join(PREVIEW_DIR, f"{scene_id}_llm.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out


def _build_prompt(
    scene_excerpt: List[Dict],
    character_meta: Dict[str, str],
    user_instructions: Optional[str] = None,
) -> str:
    lines = "\n".join(
        [
            f"{i+1}. {l.get('speaker','?')}: {l.get('text','')}"
            for i, l in enumerate(scene_excerpt)
        ]
    )
    meta = (
        "\n".join([f"- {k}: {v}" for k, v in character_meta.items()])
        if character_meta
        else "- none"
    )
    instr = (
        user_instructions.strip()
        if user_instructions
        else (
            "Correctly infer speakers, tone, and intents. Preserve voices. "
            "Return a concise JSON spec {characters:[], styles:[], notes:[]} for downstream VN rendering."
        )
    )
    return (
        "You are preparing structured guidance for a Visual Novel pipeline.\n"
        "INPUT EXCERPT:\n"
        f"{lines}\n\n"
        "CHARACTER DESCRIPTIONS:\n"
        f"{meta}\n\n"
        "TASK:\n"
        f"{instr}\n"
        "OUTPUT FORMAT:\n"
        "Return ONLY JSON with fields: characters, styles, notes. No prose."
    )


@router.post("/sample_llm")
async def sample_llm(
    payload: Dict = Body(
        ...,
        example={
            "scene_id": "rp_1234abcd",
            "excerpt": [
                {"speaker": "Alex", "text": "hey"},
                {"speaker": "Mira", "text": "sup?"},
            ],
            "character_meta": {"Alex": "shy artist", "Mira": "energetic fox girl"},
            "instructions": "Summarize tone per character and propose 3 style tags.",
            "endpoint": "http://127.0.0.1:1234/v1",
            "model": "gpt-4o-mini",
            "api_key": "",  # Optional for LM Studio
        },
    )
):
    scene_id: str = payload.get("scene_id", "")
    excerpt: List[Dict] = payload.get("excerpt", [])
    character_meta: Dict[str, str] = payload.get("character_meta", {})
    instructions: Optional[str] = payload.get("instructions")
    endpoint: str = payload.get("endpoint", "http://127.0.0.1:1234/v1")
    model: str = payload.get("model", "gpt-4o-mini")
    api_key: str = payload.get("api_key", "")

    if not excerpt and scene_id:
        # Fallback: load first 50 lines from stored scene
        scene = _load_scene(scene_id)
        excerpt = scene.get("lines", [])[:50]

    if not excerpt:
        return {"error": "No excerpt provided and scene not found."}

    prompt = _build_prompt(excerpt, character_meta, instructions)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You return strict JSON for VN rendering. No extra prose.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0)) as client:
            r = await client.post(
                f"{endpoint.rstrip('/')}/chat/completions", headers=headers, json=body
            )
            r.raise_for_status()
            resp = r.json()
    except Exception as e:
        return {"error": f"LLM request failed: {e}"}

    # Extract text
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        content = json.dumps(resp)

    out_payload = {
        "scene_id": scene_id or "adhoc",
        "created": datetime.datetime.now().isoformat(),
        "endpoint": endpoint,
        "model": model,
        "prompt": prompt,
        "excerpt": excerpt,
        "character_meta": character_meta,
        "llm_raw": content,
    }
    out_path = _save_preview(scene_id or "adhoc", out_payload)
    return {
        "status": "ok",
        "scene_id": scene_id or "adhoc",
        "preview_path": out_path,
        "llm_output": content,
    }
