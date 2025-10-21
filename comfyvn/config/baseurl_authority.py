# comfyvn/config/baseurl_authority.py
# Phase 2/2 Project Integration Chat

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional, Tuple
from urllib.parse import urlparse

DEFAULT_HOST = os.environ.get("COMFYVN_SERVER_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("COMFYVN_SERVER_PORT", "8001"))
ENV_BASE = os.environ.get("COMFYVN_BASE_URL")

try:
    from .runtime_paths import cache_dir, config_dir, settings_file
except (
    Exception
):  # pragma: no cover - runtime paths may be unavailable during bootstrap
    cache_dir = config_dir = settings_file = None  # type: ignore[assignment]

RUNTIME_CANDIDATES = [
    os.environ.get("COMFYVN_RUNTIME_STATE"),
    str(config_dir("runtime_state.json")) if callable(config_dir) else None,
    str(cache_dir("runtime_state.json")) if callable(cache_dir) else None,
    os.path.join("config", "runtime_state.json"),
    os.path.join("cache", "runtime_state.json"),
]

COMFY_CONFIG_CANDIDATES = [
    os.path.join("config", "comfyvn.json"),
    "comfyvn.json",
]

SETTINGS_CANDIDATES = [
    os.environ.get("COMFYVN_SETTINGS_FILE"),
    str(settings_file("config.json")) if callable(settings_file) else None,
    os.path.join("config", "settings", "config.json"),
    os.path.join("data", "settings", "config.json"),
]


@dataclass
class BaseAuthority:
    base_url: str
    host: str
    port: int
    source: str
    path: Optional[str] = None
    ts: float = field(default_factory=time.time)


def _load_json(path: str) -> Optional[dict]:
    try:
        if not path or not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _parse_base(base: str) -> Tuple[str, int]:
    u = urlparse(base)
    if not u.scheme:
        # allow host:port shorthand
        if ":" in base:
            host, p = base.split(":", 1)
            return host.strip(), int(p)
        return base.strip(), DEFAULT_PORT
    return (
        u.hostname or DEFAULT_HOST,
        u.port or (80 if u.scheme == "http" else 443),
    )


def _first_existing(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def _first_writable(paths):
    for p in paths:
        if not p:
            continue
        try:
            d = os.path.dirname(p) or "."
            os.makedirs(d, exist_ok=True)
            return p
        except Exception:
            continue
    # default
    if callable(config_dir):
        return str(config_dir("runtime_state.json"))
    return os.path.join("config", "runtime_state.json")


def _from_config_json() -> Optional[BaseAuthority]:
    for p in COMFY_CONFIG_CANDIDATES:
        cfg = _load_json(p)
        if not cfg:
            continue
        s = cfg.get("server", {})
        base = s.get("base_url")
        if base:
            host, port = _parse_base(base)
            return BaseAuthority(
                base_url=f"http://{host}:{port}",
                host=host,
                port=port,
                source=f"config:{p}",
                path=p,
            )
        host = s.get("host") or DEFAULT_HOST
        port = int(s.get("port") or DEFAULT_PORT)
        return BaseAuthority(
            base_url=f"http://{host}:{port}",
            host=host,
            port=port,
            source=f"config:{p}",
            path=p,
        )
    return None


def _from_settings() -> Optional[BaseAuthority]:
    for p in SETTINGS_CANDIDATES:
        cfg = _load_json(p)
        if not cfg:
            continue
        server = {}
        if isinstance(cfg, dict):
            server = cfg.get("server") or {}
        base = None
        if isinstance(server, dict):
            base = (
                server.get("base_url")
                or server.get("endpoint")
                or server.get("url")
                or None
            )
        if base:
            host, port = _parse_base(str(base))
            return BaseAuthority(
                base_url=f"http://{host}:{port}",
                host=host,
                port=port,
                source=f"settings:{p}",
                path=p,
            )
        port_val = None
        if isinstance(server, dict):
            port_val = server.get("local_port") or server.get("port")
        if port_val is None and isinstance(cfg, dict):
            port_val = cfg.get("server_port") or cfg.get("port")
        if port_val:
            try:
                port = int(port_val)
            except (TypeError, ValueError):
                continue
            host = DEFAULT_HOST
            if isinstance(server, dict):
                host = server.get("host") or host
            return BaseAuthority(
                base_url=f"http://{host}:{port}",
                host=host,
                port=port,
                source=f"settings:{p}",
                path=p,
            )
    return None


def read_authority() -> BaseAuthority:
    # 1) env
    env_base = os.environ.get("COMFYVN_BASE_URL") or ENV_BASE
    if env_base:
        host, port = _parse_base(env_base)
        return BaseAuthority(
            base_url=f"http://{host}:{port}",
            host=host,
            port=port,
            source="env:COMFYVN_BASE_URL",
        )

    # 2) runtime_state
    rp = _first_existing(RUNTIME_CANDIDATES)
    if rp:
        js = _load_json(rp) or {}
        s = js.get("server", {})
        base = s.get("base_url")
        if base:
            host, port = _parse_base(base)
            return BaseAuthority(
                base_url=f"http://{host}:{port}",
                host=host,
                port=port,
                source="runtime_state",
                path=rp,
            )

    # 3) persistent settings
    settings = _from_settings()
    if settings:
        return settings

    # 4) comfyvn.json
    c = _from_config_json()
    if c:
        return c

    # 5) default
    return BaseAuthority(
        base_url=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}",
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        source="default",
    )


def write_runtime_authority(host: str, port: int) -> str:
    rp = _first_writable(RUNTIME_CANDIDATES)
    data = {
        "server": {
            "host": host,
            "port": int(port),
            "base_url": f"http://{host}:{port}",
            "ts": time.time(),
        }
    }
    _save_json(rp, data)
    return rp


def is_port_free(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            return s.connect_ex((host, int(port))) != 0
    except Exception:
        return False


def find_open_port(host: str, start: int = 8001, tries: int = 50) -> int:
    p = int(start)
    for _ in range(tries):
        if is_port_free(host, p):
            return p
        p += 1
    return start  # fallback


@lru_cache(maxsize=1)
def _cached_authority() -> BaseAuthority:
    return read_authority()


def current_authority(refresh: bool = False) -> BaseAuthority:
    if refresh:
        _cached_authority.cache_clear()
    return _cached_authority()


def default_base_url(refresh: bool = False) -> str:
    return current_authority(refresh=refresh).base_url
