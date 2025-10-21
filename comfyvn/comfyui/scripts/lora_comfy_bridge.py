import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/scripts/lora_comfy_bridge.py
# 🧬 LoRA ↔ ComfyUI Integration Bridge (v1.0)
# Chat Source: 🧬 9. LoRA System Production Chat

import json
import os
from typing import Dict, List, Optional

import requests

from comfyvn.assets.lora_manager import LoRAManager


class LoRAComfyBridge:
    """
    Connects LoRAManager to ComfyUI backend.
    Allows listing, loading, unloading, and syncing LoRAs.
    """

    def __init__(
        self,
        comfy_api_base: str = "http://127.0.0.1:8188",
        lora_path: str = "./data/lora",
    ):
        self.base = comfy_api_base.rstrip("/")
        self.manager = LoRAManager(lora_path)
        self.session = requests.Session()
        print(f"[LoRAComfyBridge] Connected to {self.base}")

    # ------------------------------
    # 🌐 COMFYUI API HELPERS
    # ------------------------------
    def _get(self, endpoint: str) -> Optional[dict]:
        try:
            r = self.session.get(f"{self.base}/{endpoint}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[LoRAComfyBridge][ERROR] GET {endpoint}: {e}")
            return None

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        try:
            r = self.session.post(f"{self.base}/{endpoint}", json=data)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[LoRAComfyBridge][ERROR] POST {endpoint}: {e}")
            return None

    # ------------------------------
    # 🔍 DISCOVERY
    # ------------------------------
    def list_available(self) -> List[str]:
        """List all LoRAs available on ComfyUI backend."""
        resp = self._get("lora/list")
        if not resp:
            return []
        return [lora["name"] for lora in resp.get("loras", [])]

    def sync_local_to_comfy(self) -> Dict[str, dict]:
        """
        Compare local LoRA cache vs. ComfyUI registry.
        Returns missing or mismatched entries.
        """
        local_loras = self.manager.get_all()
        remote_loras = self.list_available()

        missing = {}
        for name in local_loras.keys():
            if not any(name in rl for rl in remote_loras):
                missing[name] = local_loras[name]
        print(f"[LoRAComfyBridge] {len(missing)} LoRAs missing in ComfyUI.")
        return missing

    # ------------------------------
    # ⚙️ WORKFLOW INJECTION
    # ------------------------------
    def apply_to_workflow(
        self, workflow_json: dict, lora_name: str, strength: float = 1.0
    ) -> dict:
        """
        Injects LoRA node into a given ComfyUI workflow JSON.
        Returns the updated workflow JSON.
        """
        if not lora_name.endswith((".safetensors", ".pt")):
            lora_name = f"{lora_name}.safetensors"

        node_id = str(len(workflow_json.get("nodes", [])) + 1)
        lora_node = {
            "id": node_id,
            "type": "LoraLoader",
            "inputs": {
                "lora_name": lora_name,
                "strength_model": strength,
                "strength_clip": strength,
            },
            "outputs": [],
        }
        workflow_json.setdefault("nodes", []).append(lora_node)
        print(f"[LoRAComfyBridge] Injected LoRA: {lora_name} into workflow.")
        return workflow_json

    def send_workflow(self, workflow_json: dict) -> Optional[dict]:
        """
        Sends modified workflow JSON to ComfyUI for execution.
        """
        return self._post("prompt", workflow_json)

    # ------------------------------
    # 📦 SYNC OPERATIONS
    # ------------------------------
    def register_missing_to_comfy(self):
        """
        Placeholder: Register missing local LoRAs into ComfyUI.
        Requires ComfyUI-side plugin API to support this.
        """
        missing = self.sync_local_to_comfy()
        if not missing:
            print("[LoRAComfyBridge] All local LoRAs already known to ComfyUI.")
            return

        for name, meta in missing.items():
            print(f"[LoRAComfyBridge] Would register {name} (manual copy needed).")

    # ------------------------------
    # 🔧 DEBUG
    # ------------------------------
    def status(self):
        """Show local + remote LoRA status overview."""
        local = len(self.manager.get_all())
        remote = len(self.list_available())
        print(f"[LoRAComfyBridge] Local: {local}, Remote: {remote}")
        return {"local": local, "remote": remote}
