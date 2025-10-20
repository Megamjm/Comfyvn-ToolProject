from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
from comfyvn.core.audio_stub import synth_voice
router = APIRouter(prefix="/voice", tags=["voice"])

@router.post("/speak")
def speak(body:dict=Body(...)):
    text=body.get("text",""); voice=body.get("voice","neutral")
    path=synth_voice(text, voice)
    return {"ok":True,"artifact":path}