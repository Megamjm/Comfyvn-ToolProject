# comfyvn/modules/cache_manager.py
# 🧍 Asset & Sprite System Production Chat Implementation

import os, json, time

class CacheManager:
    """Caches sprites and scene data for reuse and performance."""

    def __init__(self, cache_path="./cache/sprites"):
        self.cache_path = cache_path
        os.makedirs(cache_path, exist_ok=True)
        self.cache_index = {}

    def cache_sprite(self, sprite_id: str, sprite_data: dict):
        """Cache sprite metadata to disk."""
        path = os.path.join(self.cache_path, f"{sprite_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sprite_data, f, indent=2)
        self.cache_index[sprite_id] = {"timestamp": time.time(), "path": path}

    def load_sprite(self, sprite_id: str):
        """Load cached sprite metadata."""
        path = os.path.join(self.cache_path, f"{sprite_id}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def clear_expired(self, ttl: int = 3600):
        """Clear cache entries older than ttl (default 1 hour)."""
        now = time.time()
        for sprite_id, meta in list(self.cache_index.items()):
            if now - meta["timestamp"] > ttl:
                os.remove(meta["path"])
                del self.cache_index[sprite_id]
