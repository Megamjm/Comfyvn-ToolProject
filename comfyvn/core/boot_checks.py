from __future__ import annotations
from PySide6.QtGui import QAction
import os, socket
from pathlib import Path
from typing import Dict, Any, Iterable
from urllib.parse import urlparse

DEFAULT_DIRS = [
    "data",
    "data/templates",
    "data/worlds",
    "data/roleplay/raw",
    "data/roleplay/converted",
    "data/poses",
    "exports",
    "logs",
]

URL_VARS = [
    "COMFYUI_BASE",
    "LMSTUDIO_BASE",
    "ST_BASE",
    "RENPY_IPC",
]

def _is_valid_url(u: str) -> bool:
    try:
        p = urlparse(u)
        return bool(p.scheme and p.netloc) or (p.scheme in {"file"} and bool(p.path))
    except Exception:
        return False

def _is_free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except Exception:
            return False

class BootChecks:
    """Fail-fast environment and filesystem checks.

    Usage:
        summary = BootChecks.run(strict=False)
        # raise if critical in strict mode
    """

    @staticmethod
    def run(strict: bool = False, extra_dirs: Iterable[str] | None = None) -> Dict[str, Any]:
        created, warnings, errors = [], [], []

        dirs = list(DEFAULT_DIRS)
        if extra_dirs:
            for d in extra_dirs:
                if d not in dirs:
                    dirs.append(d)

        # Ensure dirs exist
        for d in dirs:
            p = Path(d)
            try:
                p.mkdir(parents=True, exist_ok=True)
                if not os.access(p, os.W_OK):
                    errors.append(f"Not writable: {p}")
                else:
                    created.append(str(p))
            except Exception as e:
                errors.append(f"Create failed: {p} :: {e}")

        # Validate URLs
        for var in URL_VARS:
            val = os.environ.get(var, "").strip()
            if not val:
                warnings.append(f"{var} not set")
                continue
            if not _is_valid_url(val):
                errors.append(f"Invalid URL in {var}: {val}")

        # Optional: PORT checks
        api_port = int(os.environ.get("COMFYVN_PORT", "8000") or "8000")
        if not _is_free_port(api_port):
            warnings.append(f"Port {api_port} not free; app may already run or another service bound.")

        summary = {"created_or_checked": created, "warnings": warnings, "errors": errors}
        if strict and errors:
            raise RuntimeError("BootChecks failed: " + "; ".join(errors))
        return summary