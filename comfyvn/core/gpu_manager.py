from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/gpu_manager.py
# [COMFYVN Architect | v1.0 | this chat]
from typing import Dict, Any, List

# Top 10 (preloaded) — user can customize later (plaintext creds)
DEFAULT_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "local":      {"service":"comfyui","base":"http://127.0.0.1:8188","gpu":"Auto","fields":[],"active":True, "priority":0},
    "runpod":     {"service":"runpod","base":"https://api.runpod.io/v2/","gpu":"A10G","fields":["api_key"],"active":False,"priority":10},
    "vast":       {"service":"vast.ai","base":"https://api.vast.ai/v0/","gpu":"RTX4090","fields":["api_key"],"active":False,"priority":20},
    "lambda":     {"service":"lambda","base":"https://cloud.lambdalabs.com/api/v1/","gpu":"A100","fields":["api_key"],"active":False,"priority":30},
    "paperspace": {"service":"paperspace","base":"https://api.paperspace.io","gpu":"3090","fields":["api_key"],"active":False,"priority":40},
    "coreweave":  {"service":"coreweave","base":"https://api.coreweave.com","gpu":"A40","fields":["username","password"],"active":False,"priority":50},
    "google":     {"service":"gcp","base":"https://compute.googleapis.com","gpu":"L4","fields":["service_account_json"],"active":False,"priority":60},
    "azure":      {"service":"azure","base":"https://management.azure.com","gpu":"A10","fields":["tenant_id","client_id","client_secret"],"active":False,"priority":70},
    "aws":        {"service":"aws","base":"https://ec2.amazonaws.com","gpu":"A10G","fields":["access_key","secret_key"],"active":False,"priority":80},
    "nimbix":     {"service":"nimbix","base":"https://api.nimbix.net","gpu":"A100","fields":["username","api_key"],"active":False,"priority":90},
}

def list_providers():
    return sorted(DEFAULT_PROVIDERS.items(), key=lambda kv: kv[1].get("priority",999))

def set_priority_order(names: List[str]):
    for i, n in enumerate(names):
        if n in DEFAULT_PROVIDERS:
            DEFAULT_PROVIDERS[n]["priority"] = i

def activate(name: str, active: bool):
    if name in DEFAULT_PROVIDERS:
        DEFAULT_PROVIDERS[name]["active"] = active

def get_chain() -> List[str]:
    # Return active providers in priority order
    return [name for name, meta in list_providers() if meta.get("active")]

def resolve_target() -> str:
    # First active wins
    chain = get_chain()
    return chain[0] if chain else "local"