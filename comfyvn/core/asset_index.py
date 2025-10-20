from __future__ import annotations
from PySide6.QtGui import QAction
import os, json
from pathlib import Path
from typing import Dict, Any, List

class AssetIndex:
    def __init__(self, root: str|Path = "data/assets"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_file = self.root / "_index.json"

    def build(self) -> Dict[str, Any]:
        out = {"files": []}
        for p in self.root.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(self.root))
                out["files"].append({"path": rel, "size": p.stat().st_size})
        self.index_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out

    def read(self) -> Dict[str, Any]:
        if not self.index_file.exists():
            return {"files": []}
        return json.loads(self.index_file.read_text(encoding="utf-8"))

    def sprite_path(self, char: str, mood: str) -> Path:
        safe = f"{char.strip()}_{mood.strip()}".replace(" ", "_")
        return self.root / "sprites" / f"{safe}.png"