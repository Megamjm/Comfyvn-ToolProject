# comfyvn/modules/utils_checksum.py
# 🧮 Utility Module – SHA-1 / SHA-256 Content Hashing (Patch J)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import hashlib, json
from typing import Any, Literal

def _ensure_bytes(data: Any) -> bytes:
    """
    Normalize arbitrary input into bytes for hashing.
    Accepts str, dict, list, or bytes.
    """
    if isinstance(data, bytes):
        return data
    if isinstance(data, (dict, list)):
        data = json.dumps(data, sort_keys=True, ensure_ascii=False)
    if not isinstance(data, str):
        data = str(data)
    return data.encode("utf-8")

# -------------------------------------------------
# Core Hashers
# -------------------------------------------------
def sha1(data: Any) -> str:
    """Return a SHA-1 hex digest of the given data."""
    return hashlib.sha1(_ensure_bytes(data)).hexdigest()

def sha256(data: Any) -> str:
    """Return a SHA-256 hex digest of the given data."""
    return hashlib.sha256(_ensure_bytes(data)).hexdigest()

# -------------------------------------------------
# Verification Helper
# -------------------------------------------------
def compare(a: Any, b: Any, algorithm: Literal["sha1", "sha256"] = "sha1") -> bool:
    """
    Compare two objects using the selected hash algorithm.
    Returns True if digests match.
    """
    func = sha1 if algorithm == "sha1" else sha256
    return func(a) == func(b)
