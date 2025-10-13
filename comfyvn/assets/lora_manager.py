# comfyvn/modules/lora_manager.py
# 🧬 LoRA Manager – Search, Register, and Metadata Loader (Patch D)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import os, json
from typing import List, Dict, Any


class LoRAManager:
    """
    Handles LoRA discovery, registration, and metadata management.
    Compatible with GUI /lora/* endpoints.
    """

    def __init__(self, data_path: str = "./data/lora") -> None:
        self.data_path = os.path.abspath(data_path)
        os.makedirs(self.data_path, exist_ok=True)

    # -------------------------------------------------
    # Search & Query
    # -------------------------------------------------
    def search(self, query: str) -> List[str]:
        """
        Return a sorted list of LoRA files containing the query substring.
        """
        files = [
            f
            for f in os.listdir(self.data_path)
            if f.lower().endswith((".json", ".safetensors", ".pt"))
        ]
        return sorted([f for f in files if query.lower() in f.lower()])

    # -------------------------------------------------
    # Registration & Metadata
    # -------------------------------------------------
    def register(self, name: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register or update a LoRA metadata entry.
        Saves to ./data/lora/{name}.json
        """
        path = os.path.join(self.data_path, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"[LoRAManager] Registered {name}")
        return {"registered": name, "file": path}

    def load_meta(self, name: str) -> Dict[str, Any]:
        """
        Load LoRA metadata by name.
        """
        path = os.path.join(self.data_path, f"{name}.json")
        if not os.path.exists(path):
            return {"error": "not found", "name": name}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"error": "corrupt file", "name": name}
