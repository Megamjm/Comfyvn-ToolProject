# comfyvn/config/baseurl_authority.py
# Phase 2/2 Project Integration Chat

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

from comfyvn.config import ports as ports_config


def _default_host_port() -> Tuple[str, int]:
    cfg = ports_config.get_config()
    host = str(cfg.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    ports = cfg.get("ports")
    candidate_ports: list[int] = []
    if isinstance(ports, (list, tuple)):
        for item in ports:
            try:
                value = int(item)
            except (TypeError, ValueError):
                continue
            if value not in candidate_ports and 0 < value < 65536:
                candidate_ports.append(value)
    if not candidate_ports:
        candidate_ports = [8001, 8000]
    env_port = os.environ.get("COMFYVN_SERVER_PORT")
    if env_port:
        try:
            env_value = int(env_port)
        except (TypeError, ValueError):
            env_value = None
        else:
            if env_value not in candidate_ports:
                candidate_ports.insert(0, env_value)
    return host, int(candidate_ports[0])


DEFAULT_HOST, DEFAULT_PORT = _default_host_port()
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


def _compose_base(host: str, port: str | int) -> str:
    host = (host or "").strip()
    if not host:
        host = DEFAULT_HOST
    port = str(port).strip()
    if "://" in host:
        host = host.rstrip("/")
        tail = host.rsplit(":", 1)[-1]
        if tail.isdigit() or not port:
            return host
        return f"{host}:{port}"
    scheme = "http://"
    return f"{scheme}{host}:{port}" if port else f"{scheme}{host}"


def _probe_base(base: str, *, path: str = "/health", timeout: float = 3.0) -> bool:
    if not base:
        return False
    target = base.rstrip("/") + path
    try:
        req = urllib_request.Request(target, method="GET")
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            return code is not None and 200 <= int(code) < 500
    except urllib_error.HTTPError:
        return True
    except Exception:
        return False


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
    cfg = ports_config.get_config()
    host = str(cfg.get("host") or DEFAULT_HOST).strip() or DEFAULT_HOST
    ports = cfg.get("ports")
    port = DEFAULT_PORT
    if isinstance(ports, (list, tuple)):
        for item in ports:
            try:
                port = int(item)
            except (TypeError, ValueError):
                continue
            else:
                break
    public_base = cfg.get("public_base")
    if public_base:
        base_url = str(public_base).strip().rstrip("/")
        if base_url and "://" not in base_url:
            base_url = f"http://{base_url}"
        if base_url:
            parsed = urlparse(base_url)
            if parsed.hostname and parsed.port:
                host = parsed.hostname
                port = parsed.port
            elif parsed.hostname and not parsed.port:
                host = parsed.hostname
                if parsed.scheme == "https":
                    port = 443
                elif parsed.scheme == "http":
                    port = 80
            return BaseAuthority(
                base_url=base_url.rstrip("/"),
                host=host,
                port=port,
                source="config:ports",
                path=str(ports_config.CONFIG_PATH),
            )
    return BaseAuthority(
        base_url=f"http://{host}:{port}",
        host=host,
        port=port,
        source="config:ports",
        path=str(ports_config.CONFIG_PATH),
    )


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
    try:
        cfg = ports_config.get_config()
        ports = cfg.get("ports") or ()
        normalized_ports: list[int] = []
        if isinstance(ports, (list, tuple)):
            for item in ports:
                try:
                    value = int(item)
                except (TypeError, ValueError):
                    continue
                if value not in normalized_ports:
                    normalized_ports.append(value)
        if int(port) not in normalized_ports:
            normalized_ports.insert(0, int(port))
        ports_config.record_runtime_state(
            host=host,
            ports=normalized_ports or [int(port)],
            active_port=int(port),
            base_url=f"http://{host}:{port}",
            public_base=str(cfg.get("public_base")) if cfg.get("public_base") else None,
        )
    except Exception:
        # Avoid breaking legacy call sites; record_runtime_state failures are non-fatal.
        pass
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


def discover_base(
    cli_base: str = "",
    *,
    env_var: str = "COMFYVN_BASE",
    fallback_ports: Iterable[int | str] = (8001, 8000),
) -> tuple[str, List[str], List[str]]:
    """Resolve the most appropriate server base URL.

    Returns a tuple ``(base, tried, warnings)`` mirroring the legacy
    ``tools.check_current_system._discover_base`` helper so CLI tooling can share
    the same discovery logic as the GUI.
    """

    tried: List[str] = []
    warnings: List[str] = []
    seen: set[str] = set()

    def _try_candidate(candidate: Optional[str], label: str) -> Optional[str]:
        if not candidate:
            return None
        base = str(candidate).strip().rstrip("/")
        if not base or base in seen:
            return None
        seen.add(base)
        tried.append(base)
        if _probe_base(base):
            return base
        if label:
            warnings.append(f"{label} not responding: {base}")
        return None

    if cli_base:
        base = _try_candidate(cli_base, "--base")
        return (base or ""), tried, warnings

    env_base = (os.getenv(env_var) or "").strip()
    base = _try_candidate(env_base, env_var)
    if base:
        return base, tried, warnings

    cfg = ports_config.get_config()
    public_base = (cfg.get("public_base") or "").strip()
    base = _try_candidate(public_base, "config.public_base")
    if base:
        return base, tried, warnings

    host = str(cfg.get("host") or DEFAULT_HOST).strip() or DEFAULT_HOST
    raw_ports = cfg.get("ports") or []
    for entry in raw_ports:
        try:
            candidate = str(int(entry))
        except (TypeError, ValueError):
            candidate = str(entry).strip()
        if not candidate:
            continue
        base = _try_candidate(
            _compose_base(host, candidate), f"config.ports[{candidate}]"
        )
        if base:
            return base, tried, warnings

    for fallback in fallback_ports:
        base = _try_candidate(
            _compose_base(DEFAULT_HOST, fallback), f"fallback[{fallback}]"
        )
        if base:
            return base, tried, warnings

    authority = read_authority()
    base = _try_candidate(authority.base_url, authority.source)
    if base:
        return base, tried, warnings

    return "", tried, warnings
