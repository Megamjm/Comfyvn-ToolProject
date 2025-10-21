from __future__ import annotations

import json
# comfyvn/core/scene_model.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtGui import QAction


@dataclass
class CharacterLayer:
    id: str
    src: str
    x: int = 0
    y: int = 0
    scale: float = 1.0
    z: int = 1


@dataclass
class Dialogue:
    speaker: str = ""
    text: str = ""


@dataclass
class SceneDoc:
    background: str = ""
    characters: List[CharacterLayer] = field(default_factory=list)
    dialogue: Dialogue = field(default_factory=Dialogue)
    meta: Dict[str, Any] = field(default_factory=dict)


def load_scene(path: str | Path) -> SceneDoc:
    p = Path(path)
    if not p.exists():
        return SceneDoc()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return SceneDoc()
    bg = data.get("background", "")
    chars = [
        CharacterLayer(
            id=c.get("id", "char"),
            src=c.get("src", ""),
            x=int(c.get("x", 0)),
            y=int(c.get("y", 0)),
            scale=float(c.get("scale", 1.0)),
            z=int(c.get("z", 1)),
        )
        for c in data.get("characters", [])
    ]
    d = data.get("dialogue", {}) or {}
    dlg = Dialogue(speaker=d.get("speaker", ""), text=d.get("text", ""))
    return SceneDoc(
        background=bg, characters=chars, dialogue=dlg, meta=data.get("meta", {})
    )
