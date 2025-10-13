# comfyvn/modules/cache_manager.py
# 🧩 Cache Manager – Persistent Asset Caching + TTL Cleanup (Patch P)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import os, json, time
from typing import Optional, Dict, Any


class CacheManager:
    """Caches sprites and scene data for reuse and performance."""

    def __init__(
        self, cache_path: str = "./cache/sprites", index_file: str = "cache_index.json"
    ):
        self.cache_path = os.path.abspath(cache_path)
        self.index_path = os.path.join(self.cache_path, index_file)
        os.makedirs(self.cache_path, exist_ok=True)
        self.cache_index: Dict[str, Dict[str, Any]] = {}
        self._load_index()
        print(f"[CacheManager] Initialized cache at {self.cache_path}")

    # -------------------------------------------------
    # Sprite Cache
    # -------------------------------------------------
    def cache_sprite(self, sprite_id: str, sprite_data: dict) -> str:
        """Cache sprite metadata to disk and update index."""
        path = os.path.join(self.cache_path, f"{sprite_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(sprite_data, f, indent=2, ensure_ascii=False)
            entry = {"timestamp": time.time(), "path": path, "access_time": time.time()}
            self.cache_index[sprite_id] = entry
            self._save_index()
            print(f"[CacheManager] Cached sprite '{sprite_id}' → {path}")
            return path
        except Exception as e:
            print(f"[CacheManager] Error caching {sprite_id}: {e}")
            return ""

    def load_sprite(self, sprite_id: str) -> Optional[dict]:
        """Load cached sprite metadata and update access time."""
        entry = self.cache_index.get(sprite_id)
        if not entry:
            path = os.path.join(self.cache_path, f"{sprite_id}.json")
            if not os.path.exists(path):
                return None
            entry = {"timestamp": time.time(), "path": path}
            self.cache_index[sprite_id] = entry

        try:
            with open(entry["path"], "r", encoding="utf-8") as f:
                data = json.load(f)
            entry["access_time"] = time.time()
            self._save_index()
            print(f"[CacheManager] Loaded sprite '{sprite_id}'")
            return data
        except Exception as e:
            print(f"[CacheManager] Error loading {sprite_id}: {e}")
            return None

    # -------------------------------------------------
    # Expiry & Maintenance
    # -------------------------------------------------
    def clear_expired(self, ttl: int = 3600) -> int:
        """Clear cache entries older than ttl (default 1 hour)."""
        now = time.time()
        removed = 0
        for sprite_id, meta in list(self.cache_index.items()):
            if now - meta.get("timestamp", now) > ttl:
                try:
                    os.remove(meta["path"])
                except Exception:
                    pass
                del self.cache_index[sprite_id]
                removed += 1
        if removed:
            self._save_index()
            print(f"[CacheManager] Cleared {removed} expired entries")
        return removed

    def purge_all(self) -> int:
        """Completely clears the cache folder and index."""
        removed = 0
        for file in os.listdir(self.cache_path):
            if file.endswith(".json"):
                try:
                    os.remove(os.path.join(self.cache_path, file))
                    removed += 1
                except Exception:
                    pass
        self.cache_index.clear()
        self._save_index()
        print(f"[CacheManager] Purged {removed} files from cache")
        return removed

    # -------------------------------------------------
    # Index Persistence
    # -------------------------------------------------
    def _save_index(self):
        try:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(self.cache_index, f, indent=2)
        except Exception as e:
            print(f"[CacheManager] Failed to save index: {e}")

    def _load_index(self):
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    self.cache_index = json.load(f)
                print(f"[CacheManager] Loaded {len(self.cache_index)} cache entries")
            except Exception as e:
                print(f"[CacheManager] Index load error: {e}")
