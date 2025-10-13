# comfyvn/modules/lora_manager.py
# 🧬 LoRA System Production Chat Implementation (v1.0)
# Chat Source: 🧬 9. LoRA System Production Chat

import os
import json
import hashlib
import shutil
from typing import List, Dict, Optional


class LoRAManager:
    """
    Handles discovery, registration, and caching of LoRA models.
    Integrates with ComfyUI for automatic injection or listing.
    """

    def __init__(self, data_path: str = "./data/lora"):
        self.data_path = data_path
        os.makedirs(self.data_path, exist_ok=True)
        self.index_path = os.path.join(self.data_path, "index.json")

        # Load LoRA index
        if os.path.exists(self.index_path):
            with open(self.index_path, "r", encoding="utf-8") as f:
                self.index = json.load(f)
        else:
            self.index = {}
            self._save_index()

    # ------------------------------
    # 🔍 SEARCH & DISCOVERY
    # ------------------------------
    def search(self, query: str) -> List[Dict]:
        """Search LoRA metadata and filenames."""
        results = []
        for name, meta in self.index.items():
            if (
                query.lower() in name.lower()
                or query.lower() in json.dumps(meta).lower()
            ):
                results.append({"name": name, "meta": meta})
        return results

    def discover_local(self) -> List[str]:
        """Scan the local /data/lora directory for LoRA files."""
        all_files = os.listdir(self.data_path)
        return [f for f in all_files if f.endswith((".safetensors", ".pt", ".ckpt"))]

    # ------------------------------
    # 📦 REGISTRATION & INDEXING
    # ------------------------------
    def register(self, name: str, meta: Dict):
        """Register LoRA metadata in the index."""
        self.index[name] = meta
        self._save_index()
        print(f"[LoRA] Registered: {name}")

    def unregister(self, name: str):
        """Remove LoRA metadata and cached file if desired."""
        if name in self.index:
            del self.index[name]
            self._save_index()
            print(f"[LoRA] Unregistered: {name}")

    # ------------------------------
    # 🧠 CACHING & HASHING
    # ------------------------------
    def compute_hash(self, file_path: str) -> str:
        """Generate SHA1 hash for a given LoRA file."""
        BUF_SIZE = 65536
        sha1 = hashlib.sha1()
        with open(file_path, "rb") as f:
            while chunk := f.read(BUF_SIZE):
                sha1.update(chunk)
        return sha1.hexdigest()

    def cache_lora(self, source_path: str, name: Optional[str] = None):
        """Copy LoRA into cache directory and auto-register."""
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source file not found: {source_path}")

        name = name or os.path.basename(source_path)
        dest_path = os.path.join(self.data_path, name)
        shutil.copy2(source_path, dest_path)
        file_hash = self.compute_hash(dest_path)

        meta = {
            "file": name,
            "hash": file_hash,
            "size_kb": os.path.getsize(dest_path) // 1024,
        }
        self.register(name, meta)
        return meta

    # ------------------------------
    # 🌐 REMOTE INTEGRATION (Placeholder)
    # ------------------------------
    def fetch_from_repo(self, repo_url: str, query: str):
        """
        Placeholder for future HuggingFace / civitai integration.
        """
        print(
            f"[LoRA] Remote fetch from {repo_url} with query '{query}' (not implemented)."
        )
        return []

    # ------------------------------
    # ⚙️ INTERNAL UTILITIES
    # ------------------------------
    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, indent=2)

    def get_all(self) -> Dict[str, Dict]:
        """Return all indexed LoRA metadata."""
        return self.index

    def __repr__(self):
        return f"<LoRAManager LoRAs={len(self.index)} path={self.data_path}>"
