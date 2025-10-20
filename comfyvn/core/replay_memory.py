from __future__ import annotations
from PySide6.QtGui import QAction
import time, json
from pathlib import Path
from typing import Dict, Any, List

DEFAULT_DIR = Path("./data/replays")

class ReplayMemory:
    def __init__(self, root: str|Path = DEFAULT_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        safe = "".join(c for c in name if c.isalnum() or c in ("-", "_"))
        return self.root / f"{safe}.jsonl"

    def append(self, name: str, event: Dict[str, Any]) -> None:
        event = dict(event or {})
        event.setdefault("ts", time.time())
        with self._path(name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def read(self, name: str, limit: int|None=None) -> List[Dict[str, Any]]:
        p = self._path(name)
        if not p.exists(): return []
        out: List[Dict[str, Any]] = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                try: out.append(json.loads(line))
                except Exception: pass
        return out[-limit:] if limit else out

    def list(self) -> list[str]:
        return [p.stem for p in self.root.glob("*.jsonl")]