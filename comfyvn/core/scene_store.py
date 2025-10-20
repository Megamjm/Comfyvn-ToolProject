from __future__ import annotations
from PySide6.QtGui import QAction
import json, time
from pathlib import Path
from typing import Dict, Any, List

DEFAULT_DIR = Path("./data/scenes")

class SceneStore:
    def __init__(self, root: str|Path = DEFAULT_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, scene_id: str, data: Dict[str, Any]) -> str:
        safe = "".join(c for c in scene_id if c.isalnum() or c in ("-", "_"))
        p = self.root / f"{safe}.json"
        data = dict(data or {})
        data.setdefault("updated", time.time())
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return safe

    def load(self, scene_id: str) -> Dict[str, Any]:
        p = self.root / f"{scene_id}.json"
        if not p.exists(): return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def list(self) -> List[str]:
        return [p.stem for p in self.root.glob("*.json")]