from PySide6.QtGui import QAction
from fastapi import APIRouter, Body
from comfyvn.core.memory_engine import Voices, remember_event

router = APIRouter()

@router.get("/voice/list")
def list_voices():
    return {"ok": True, "items": Voices.all()}

@router.post("/voice/profile")
def set_profile(payload: dict = Body(...)):
    name = payload.get("name","default")
    Voices.set(name, payload)
    remember_event("voice.profile", {"name": name})
    return {"ok": True, "name": name}

@router.post("/voice/speak")
def speak(payload: dict = Body(...)):
    text = payload.get("text","")
    voice = payload.get("voice","default")
    return {"ok": True, "voice": voice, "text": text, "path": f"data/tts/{voice}_sample.wav"}