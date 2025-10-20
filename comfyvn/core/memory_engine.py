from PySide6.QtGui import QAction
from pathlib import Path
import json, time

BASE = Path("data/memory"); BASE.mkdir(parents=True, exist_ok=True)

class KV:
    def __init__(self, name: str):
        self.p = BASE / f"{name}.json"
        if not self.p.exists(): self.p.write_text("{}", encoding="utf-8")
    def get(self, key: str, default=None):
        d = json.loads(self.p.read_text())
        return d.get(key, default)
    def set(self, key: str, value):
        d = json.loads(self.p.read_text())
        d[key] = value
        self.p.write_text(json.dumps(d, indent=2), encoding="utf-8")
        return value
    def all(self):
        return json.loads(self.p.read_text())

Personas = KV("personas")
Lore     = KV("lore")
Voices   = KV("voices")

def remember_event(kind: str, data: dict):
    log = BASE / "events.log"
    log.write_text((log.read_text() if log.exists() else "") + json.dumps(
        {"ts": time.time(), "kind": kind, "data": data}) + "\n", encoding="utf-8")