# comfyvn/modules/core/data_bootstrap.py
# ⚙️ 3. Server Core Production Chat — Data Bootstrap & Integrity Manager
# Ensures /comfyvn/data contains all essential runtime data, auto-restored if missing or corrupted.

from __future__ import annotations
import os, json, shutil, hashlib
from typing import Dict, Any

DATA_PATH = "./comfyvn/data"
DEFAULTS_PATH = "./comfyvn/defaults"

REQUIRED_FILES = {
    "styles_registry.json": "Default style registry.",
    "community_assets_registry.json": "Default asset registry.",
    "legal_disclaimer.txt": "Default legal disclaimer.",
    "nodes_registry.json": "Runtime node registry.",
    "meta_version.json": "Local data manifest.",
}


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _json_load_safe(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def ensure_data_integrity(
    restore_missing=True, overwrite_invalid=True
) -> Dict[str, Any]:
    """Check and repair data files under comfyvn/data."""
    os.makedirs(DATA_PATH, exist_ok=True)
    os.makedirs(DEFAULTS_PATH, exist_ok=True)

    report = {"checked": [], "restored": [], "skipped": [], "hashes": {}}

    for fname, desc in REQUIRED_FILES.items():
        target = os.path.join(DATA_PATH, fname)
        default = os.path.join(DEFAULTS_PATH, fname)
        report["checked"].append(fname)

        # Missing file
        if not os.path.exists(target):
            if restore_missing and os.path.exists(default):
                shutil.copy2(default, target)
                report["restored"].append(fname)
            continue

        # Corrupted / unreadable JSON
        if fname.endswith(".json"):
            obj = _json_load_safe(target)
            if obj is None or (isinstance(obj, dict) and not obj):
                if overwrite_invalid and os.path.exists(default):
                    shutil.copy2(default, target)
                    report["restored"].append(fname)

        report["hashes"][fname] = _hash_file(target) if os.path.exists(target) else None

    return report
