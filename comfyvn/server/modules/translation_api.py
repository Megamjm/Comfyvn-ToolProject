from typing import Any, Dict, List

# comfyvn/server/modules/translation_api.py
from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

router = APIRouter()


@router.post("/translate")
def translate(body: Dict[str, Any] = Body(...)):
    # stub: echo back
    txt = str(body.get("text", ""))
    lang = body.get("target", "en")
    return {"ok": True, "lang": lang, "text": txt}


@router.post("/import/pak")
def import_pak(body: Dict[str, Any] = Body(...)):
    # stub: pretend to parse scenes
    name = body.get("name", "pak")
    scenes = [
        {
            "scene_id": "imported_intro",
            "title": "Imported Intro",
            "lines": [{"speaker": "narrator", "text": "Imported."}],
        }
    ]
    return {"ok": True, "name": name, "scenes": scenes}
