# comfyvn/modules/audio_cache.py
# 💾 Audio cache (download/link), tagging, pruning, preview paths
# [⚙️ 3. Server Core Production Chat]

from __future__ import annotations
import os, json, asyncio, hashlib
from pathlib import Path
from typing import Dict, List, Optional
import httpx

CACHE_ROOT = Path("./data/audio/cache").resolve()
INDEX_PATH = CACHE_ROOT / "index.json"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
if not INDEX_PATH.exists():
    INDEX_PATH.write_text("{}", encoding="utf-8")

def _read_index() -> Dict:
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _write_index(data: Dict) -> None:
    INDEX_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _safe_name(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in ("-","_","."))[:120]

class AudioCache:
    """
    Caches downloaded audio assets and their metadata; tracks usage;
    supports pruning to avoid bloat.
    """

    def __init__(self):
        self.index = _read_index()

    def list_cached(self) -> List[Dict]:
        return list(self.index.values())

    def get(self, asset_id: str) -> Optional[Dict]:
        return self.index.get(asset_id)

    async def download(self, asset: Dict) -> Dict:
        """Download (or re-use) an asset; record metadata & tags."""
        asset_id = asset["id"]
        fmt = asset.get("format", "mp3")
        provider = asset.get("provider","misc")
        fname = _safe_name(f"{provider}_{asset_id}.{fmt}")
        fpath = CACHE_ROOT / fname

        # if already present, bump usage
        if asset_id in self.index and fpath.exists():
            rec = self.index[asset_id]
            rec["usage_count"] = int(rec.get("usage_count",0)) + 1
            _write_index(self.index)
            return rec

        # need to fetch
        url = asset.get("download_url") or asset.get("preview_url")
        if not url:
            raise RuntimeError("Asset missing download_url/preview_url")

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            fpath.write_bytes(r.content)

        # record
        rec = {
            "id": asset_id,
            "title": asset.get("title"),
            "file": str(fpath),
            "provider": provider,
            "license": asset.get("license"),
            "category": asset.get("category"),
            "tags": asset.get("tags", []),
            "duration_sec": asset.get("duration_sec"),
            "usage_count": 1,
        }
        self.index[asset_id] = rec
        _write_index(self.index)
        return rec

    def tag(self, asset_id: str, add_tags: List[str]) -> Dict:
        rec = self.index.get(asset_id)
        if not rec: raise FileNotFoundError("Not cached")
        tags = set(rec.get("tags", []))
        tags.update(add_tags)
        rec["tags"] = sorted(tags)
        _write_index(self.index)
        return rec

    def prune(self, max_items: int = 200, min_usage: int = 1) -> Dict:
        """Remove least-used beyond max_items; keep anything with usage >= min_usage."""
        items = list(self.index.values())
        # keep highly-used first
        items.sort(key=lambda r: (-(r.get("usage_count",0)), r.get("title","")))
        keep = items[:max_items]
        keep_ids = {r["id"] for r in keep}
        removed = []
        for aid, rec in list(self.index.items()):
            if aid not in keep_ids and int(rec.get("usage_count",0)) < min_usage:
                try:
                    f = Path(rec["file"])
                    if f.exists(): f.unlink()
                except Exception:
                    pass
                removed.append(aid)
                del self.index[aid]
        _write_index(self.index)
        return {"kept": len(keep), "removed": removed}

    def preview_path(self, asset_id: str) -> Optional[str]:
        rec = self.index.get(asset_id)
        return rec.get("file") if rec else None
