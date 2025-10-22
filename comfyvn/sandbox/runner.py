from __future__ import annotations

import importlib
import os
import signal
import sys
import time
import types
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtGui import QAction

from comfyvn.config import feature_flags
from comfyvn.security.sandbox import apply_network_policy

DEFAULTS = {
    "cpu_secs": int(os.getenv("SANDBOX_CPU_SECS", "10")),
    "wall_secs": int(os.getenv("SANDBOX_WALL_SECS", "15")),
    "mem_mb": int(os.getenv("SANDBOX_MEM_MB", "512")),
    "network": os.getenv("SANDBOX_NETWORK", "0") == "1",
    "network_allow": tuple(
        item.strip()
        for item in os.getenv("SANDBOX_NETWORK_ALLOW", "").split(",")
        if item.strip()
    ),
    "fs_roots": os.getenv("SANDBOX_FS_ROOTS", "./exports,./data/assets").split(","),
    "env_allow": os.getenv("SANDBOX_ENV_ALLOW", "PATH,HOME").split(","),
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_allowlist(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        cand = value.strip()
        return [cand] if cand else []
    if isinstance(value, (list, tuple, set)):
        out = []
        for entry in value:
            cand = str(entry).strip()
            if cand:
                out.append(cand)
        return out
    cand = str(value).strip()
    return [cand] if cand else []


def _apply_limits(cpu_secs: int, wall_secs: int, mem_mb: int):
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (cpu_secs, cpu_secs))
        bs = mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (bs, bs))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except Exception:
        pass

    def _alarm_handler(signum, frame):
        raise TimeoutError("wall clock limit exceeded")

    try:
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(max(1, int(wall_secs)))
    except Exception:
        pass


def _patch_subprocess():
    import subprocess

    def _block(*a, **kw):
        raise RuntimeError("subprocess disabled by sandbox")

    subprocess.Popen = _block  # type: ignore
    subprocess.call = _block  # type: ignore
    subprocess.check_call = _block  # type: ignore
    subprocess.check_output = _block  # type: ignore


def _patch_open(roots: List[str]):
    import builtins
    import os as _os

    roots = [_os.path.abspath(r.strip()) for r in roots if r.strip()]

    def allowed(path: str) -> bool:
        ap = _os.path.abspath(path)
        for r in roots:
            if ap.startswith(r):
                return True
        return False

    _orig_open = builtins.open

    def safe_open(file, mode="r", *a, **kw):
        # allow reads of stdlib and cwd; restrict writes to roots
        if any(m in mode for m in ("w", "a", "+")):
            if not allowed(file):
                raise PermissionError(f"write blocked outside allowed roots: {file}")
        return _orig_open(file, mode, *a, **kw)

    builtins.open = safe_open  # type: ignore


def _scrub_env(allow: List[str]):
    keep = {k: v for k, v in os.environ.items() if k in allow}
    os.environ.clear()
    os.environ.update(keep)
    os.environ["COMFYVN_SANDBOX"] = "1"


def run(
    module: str, func: str, payload: Dict[str, Any], perms: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    p = perms or {}
    cpu = int(p.get("cpu_secs", DEFAULTS["cpu_secs"]))
    wall = int(p.get("wall_secs", DEFAULTS["wall_secs"]))
    mem = int(p.get("mem_mb", DEFAULTS["mem_mb"]))
    net = _as_bool(p.get("network", DEFAULTS["network"]))
    net_allow = _normalize_allowlist(p.get("network_allow", DEFAULTS["network_allow"]))
    roots = list(p.get("fs_roots", DEFAULTS["fs_roots"]))
    env_allow = list(p.get("env_allow", DEFAULTS["env_allow"]))

    _apply_limits(cpu, wall, mem)
    guard_enabled = feature_flags.is_enabled(
        "enable_security_sandbox_guard", default=True
    )
    if guard_enabled:
        apply_network_policy(net, net_allow)
    else:
        apply_network_policy(net, ["*"] if net else [])
    _patch_subprocess()
    _patch_open(roots)
    _scrub_env(env_allow)

    mod = importlib.import_module(module)
    fn = getattr(mod, func)
    if not callable(fn):
        raise TypeError("entry is not callable")
    out = fn(payload, payload.get("id") if isinstance(payload, dict) else None)
    if not isinstance(out, dict):
        out = {"ok": True, "result": out}
    return out
