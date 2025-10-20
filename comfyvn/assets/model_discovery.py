from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/modules/model_discovery.py
# Model/Lora discovery + integrity scanning + Safe Mode filter
# ComfyVN_Architect (Asset Sprite Research Branch)

import os, hashlib, json
from typing import Dict, List, Optional

DEFAULT_PATHS = {
    "checkpoints": [
        "./models/checkpoints",
        "./models/Stable-diffusion",
        "~/ComfyUI/models/checkpoints",
    ],
    "loras": ["./models/loras", "~/ComfyUI/models/loras"],
    "controlnets": ["./models/controlnet", "~/ComfyUI/models/controlnet"],
}

EXTS = {
    "checkpoint": (".safetensors", ".ckpt"),
    "lora": (".safetensors", ".pt"),
    "control": (".safetensors", ".pth", ".pt"),
}

COMMUNITY_ASSET_PATH = "./comfyvn/data/community_assets_registry.json"
SAFE_MODE_ENV = "COMFYVN_SAFE_MODE"


def _expand(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def list_models(paths: Dict[str, List[str]] = None) -> Dict[str, List[str]]:
    """Return discovered models by category (local filesystem only)."""
    paths = paths or DEFAULT_PATHS
    out = {"checkpoints": [], "loras": [], "controlnets": []}
    for cat in out.keys():
        for base in paths.get(cat, []):
            p = _expand(base)
            if not os.path.isdir(p):
                continue
            for root, _, files in os.walk(p):
                for f in files:
                    fn = f.lower()
                    fp = os.path.join(root, f)
                    if cat == "checkpoints" and fn.endswith(EXTS["checkpoint"]):
                        out["checkpoints"].append(fp)
                    elif cat == "loras" and fn.endswith(EXTS["lora"]):
                        out["loras"].append(fp)
                    elif cat == "controlnets" and fn.endswith(EXTS["control"]):
                        out["controlnets"].append(fp)
    return out


def verify_integrity(file_list: List[str]) -> Dict[str, str]:
    """Return sha256 map for provided files."""
    hmap = {}
    for p in file_list:
        try:
            hmap[p] = _sha256(p)
        except Exception:
            hmap[p] = "unreadable"
    return hmap


def safe_mode_enabled() -> bool:
    return os.getenv(SAFE_MODE_ENV, "0") in ("1", "true", "True")


def filter_verified_assets(registry: Dict) -> Dict[str, List[Dict]]:
    """
    In Safe Mode, return only verified entries (ignore user/unverified).
    For UI reference; filesystem models are independent of this.
    """
    verified = registry.get("verified_assets", [])
    user = registry.get("unverified_user", [])
    if safe_mode_enabled():
        return {"verified": verified, "user": []}
    return {"verified": verified, "user": user}


def load_community_registry() -> Dict:
    try:
        with open(COMMUNITY_ASSET_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"verified_assets": [], "unverified_user": []}