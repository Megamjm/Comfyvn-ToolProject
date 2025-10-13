# comfyvn/server/modules/playground_api.py
# 🧪 Playground API — REST endpoints for PlaygroundWindow
from fastapi import APIRouter, HTTPException, Request
import os, json
from comfyvn.assets.playground_manager import PlaygroundManager

router = APIRouter(prefix="/playground", tags=["Playground"])


@router.get("/checkpoints")
async def list_checkpoints():
    return {"models": ["checkpoint_A.safetensors", "checkpoint_B.safetensors"]}


@router.get("/loras")
async def list_loras():
    return {"models": ["lora_A", "lora_B"]}


@router.get("/controlnets")
async def list_controlnets():
    return {"models": ["canny", "depth", "openpose"]}


@router.post("/apply/{scene_id}")
async def apply_scene(scene_id: str, request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")
    pm = PlaygroundManager()
    result = pm.apply_prompt(scene_id, prompt)
    return result
