# comfyvn/server/routes/st_bridge.py
# 🌉 SillyTavern → ComfyVN Bridge Importer
# [🌍 World Lore Production Chat | v1.0.3 Stable Panel Integration]

from fastapi import APIRouter, Request
from comfyvn.core.world_loader import WorldLoader
from comfyvn.assets.persona_manager import PersonaManager
from comfyvn.assets.playground_manager import PlaygroundManager

router = APIRouter(prefix="/st", tags=["SillyTavern Bridge"])

world_loader = WorldLoader()
persona_mgr = PersonaManager()
playground_mgr = PlaygroundManager()


@router.post("/import")
async def import_from_st(request: Request):
    """Handle incoming data from SillyTavern extension."""
    payload = await request.json()
    dtype = payload.get("type")
    data = payload.get("data", {})

    if dtype == "worlds":
        # Save world data into /data/worlds/
        for wname, wdata in data.items():
            world_loader.save_world(wname, wdata)
        return {"status": "ok", "imported": len(data), "type": dtype}

    elif dtype == "characters":
        # Optional: write to /data/characters/
        path = "./data/characters"
        import os, json

        os.makedirs(path, exist_ok=True)
        for cname, cdata in data.items():
            with open(f"{path}/{cname}.json", "w", encoding="utf-8") as f:
                json.dump(cdata, f, indent=2)
        return {"status": "ok", "imported": len(data), "type": dtype}

    elif dtype == "personas":
        # Register personas via PersonaManager
        for persona in data.get("personas", []):
            persona_mgr.register_persona(persona)
        return {
            "status": "ok",
            "imported": len(data.get("personas", [])),
            "type": dtype,
        }

    elif dtype == "active":
        active_world = data.get("active_world")
        if active_world:
            world_loader.active_world = active_world
        return {"status": "ok", "active_world": active_world}

    return {"status": "ignored", "reason": "unknown type", "type": dtype}
