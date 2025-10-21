import json
from pathlib import Path

from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

from comfyvn.core.i18n import export_strings, pack_locale, translate_strings

router = APIRouter(prefix="/i18n", tags=["i18n"])


@router.post("/export")
def export_scene(body: dict = Body(...)):
    return {"ok": True, **export_strings(body or {})}


@router.post("/translate")
def translate(body: dict = Body(...)):
    strings = body.get("strings", [])
    lang = body.get("lang", "en")
    return {"ok": True, "pairs": translate_strings(strings, lang)}


@router.post("/pack")
def pack(body: dict = Body(...)):
    scene_id = body.get("scene_id", "scene")
    lang = body.get("lang", "en")
    pairs = body.get("pairs", [])
    path = pack_locale(scene_id, pairs, lang)
    return {"ok": True, "bundle": path}
