import json
from pathlib import Path

from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()
EV_DIR = Path("./data/jobs")
EV_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/health")
def health():
    return {"ok": True, "dir": str(EV_DIR)}


@router.get("/poll")
def poll(limit: int = 20):
    files = sorted(EV_DIR.glob("*.json"))[: max(1, min(limit, 100))]
    events = []
    for f in files:
        try:
            events.append(json.loads(f.read_text(encoding="utf-8")))
            f.unlink()
        except Exception:
            pass
    return {"ok": True, "events": events}


EventsRouter = router
