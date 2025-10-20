from __future__ import annotations
from PySide6.QtGui import QAction
import json, time
from pathlib import Path
from typing import Dict, Any, List

DEFAULT_DIR = Path("./data/jobs/feedback")

class FeedbackTracker:
    def __init__(self, root: str|Path = DEFAULT_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _file(self, job_id: str) -> Path:
        safe = "".join(c for c in job_id if c.isalnum() or c in ("-", "_"))
        return self.root / f"{safe}.jsonl"

    def append(self, job_id: str, msg: Dict[str, Any]):
        msg["ts"] = time.time()
        with self._file(job_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def read(self, job_id: str, limit: int|None = None) -> List[Dict[str, Any]]:
        p = self._file(job_id)
        if not p.exists(): return []
        lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        return lines[-limit:] if limit else lines

    def list_jobs(self) -> List[str]:
        return [p.stem for p in self.root.glob("*.jsonl")]