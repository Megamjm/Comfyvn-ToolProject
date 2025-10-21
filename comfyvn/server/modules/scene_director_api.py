from fastapi import APIRouter, Body, HTTPException
from PySide6.QtGui import QAction

from comfyvn.core.memory_engine import Lore, Personas, Voices, remember_event

router = APIRouter()


@router.post("/director/compose")
def compose(payload: dict = Body(...)):
    chars = payload.get("characters", [])
    context = payload.get("context", "")
    if not chars:
        raise HTTPException(400, "characters required")
    personas = {c: Personas.get(c, {}) for c in chars}
    world = payload.get("world", "default")
    lore = Lore.get(world, {"entries": []})
    mood = payload.get("mood", "neutral")
    lines = []
    for c in chars:
        trait = personas.get(c, {}).get("trait", "plain")
        lines.append(
            {"speaker": c, "text": f"{c} ({trait}, {mood}): reacts to '{context}'"}
        )
    remember_event("director.compose", {"chars": chars, "world": world})
    return {
        "ok": True,
        "world": world,
        "lore_refs": len(lore.get("entries", [])),
        "lines": lines,
    }
