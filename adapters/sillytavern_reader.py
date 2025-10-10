from __future__ import annotations
import os, json, glob
from typing import Iterator, Dict, Any

def iter_jsonl(path:str) -> Iterator[Dict[str,Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def load_chats(chats_dir:str) -> list[dict]:
    chats = []
    for p in glob.glob(os.path.join(chats_dir, "*.jsonl")):
        chats.append({
            "path": p,
            "items": list(iter_jsonl(p))
        })
    return chats

def to_beats(chat_items:list[dict]) -> list[dict]:
    beats = []
    for i, msg in enumerate(chat_items, 1):
        role = msg.get("role") or msg.get("author") or "unknown"
        content = msg.get("content") or msg.get("text") or ""
        char = msg.get("name") or msg.get("character") or role
        beats.append({
            "id": f"b{i:04d}",
            "timecode": "",
            "line": content,
            "characters": [{"name": char}],
            "shot": None
        })
    return beats
