# comfyvn/modules/asset_index.py
# Asset Index system (persistent registry of exports)
# ComfyVN_Architect (Asset Sprite Research Branch)

import os, json, time, hashlib
from typing import Dict, Any, List, Optional

INDEX_PATH = "./comfyvn/data/assets_index.json"

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _ensure_dir():
    d = os.path.dirname(INDEX_PATH)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def load_index() -> Dict[str, Any]:
    _ensure_dir()
    if not os.path.exists(INDEX_PATH):
        return {"version": 1, "items": []}
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_index(idx: Dict[str, Any]) -> None:
    _ensure_dir()
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)

def add_record(item: Dict[str, Any]) -> None:
    idx = load_index()
    item.setdefault("timestamp", _now_iso())
    idx["items"].append(item)
    # optional: cap/rotation policy could go here
    save_index(idx)

def query_index(
    *,
    type_: Optional[str] = None,
    style_id: Optional[str] = None,
    character_id: Optional[str] = None,
    scene_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    idx = load_index()
    results = []
    for it in idx.get("items", []):
        if type_ and it.get("type") != type_:
            continue
        if style_id and it.get("style_id") != style_id:
            continue
        if character_id and it.get("character", {}).get("id") != character_id:
            continue
        if scene_id and it.get("scene_id") != scene_id:
            continue
        results.append(it)
    return results