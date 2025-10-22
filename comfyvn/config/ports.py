from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse

CONFIG_PATH = Path("config/comfyvn.json")
CONFIG_CANDIDATES: tuple[Path, ...] = (CONFIG_PATH, Path("comfyvn.json"))
RUNTIME_FILE = Path(".runtime/last_server.json")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORTS: tuple[int, int] = (8001, 8000)

ENV_HOST = "COMFYVN_HOST"
ENV_PORTS = "COMFYVN_PORTS"
ENV_BASE = "COMFYVN_BASE"


@dataclass(frozen=True)
class PortsConfig:
    host: str
    ports: tuple[int, ...]
    public_base: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "ports": list(self.ports),
            "public_base": self.public_base,
        }


def _load_raw_config() -> dict:
    for path in CONFIG_CANDIDATES:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError:
            continue
    return {}


def _normalise_ports(values: Iterable[int | str]) -> tuple[int, ...]:
    result: list[int] = []
    for value in values:
        try:
            port = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if port <= 0 or port > 65535:
            continue
        if port not in result:
            result.append(port)
    if result:
        return tuple(result)
    return DEFAULT_PORTS


def _parse_env_ports(value: str) -> tuple[int, ...]:
    tokens: list[str] = []
    for separator in (",", ";"):
        if separator in value:
            tokens = value.replace(";", ",").split(",")
            break
    if not tokens:
        tokens = value.split()
    if not tokens:
        tokens = [value]
    return _normalise_ports(tokens)


def _apply_env_overrides(cfg: PortsConfig) -> PortsConfig:
    host = cfg.host
    ports = cfg.ports
    public_base = cfg.public_base

    env_host = os.getenv(ENV_HOST)
    if env_host:
        host = env_host.strip() or host

    env_ports = os.getenv(ENV_PORTS)
    if env_ports:
        ports = _parse_env_ports(env_ports)

    env_base = os.getenv(ENV_BASE)
    if env_base:
        trimmed = env_base.strip()
        public_base = trimmed or None
        if trimmed:
            parsed = urlparse(trimmed)
            if parsed.hostname:
                host = parsed.hostname
            if parsed.port and parsed.port not in ports:
                ports = (parsed.port, *ports)

    return PortsConfig(host=host, ports=ports, public_base=public_base)


def _config_section(payload: Mapping[str, object]) -> Mapping[str, object]:
    server = payload.get("server")
    if isinstance(server, Mapping):
        return server
    return {}


def _derive_config() -> PortsConfig:
    payload = _load_raw_config()
    section = _config_section(payload)

    host = str(section.get("host") or DEFAULT_HOST)
    ports_raw = section.get("ports")
    if isinstance(ports_raw, Sequence) and not isinstance(ports_raw, (str, bytes)):
        ports = _normalise_ports(ports_raw)
    else:
        port_value = section.get("port") or section.get("server_port")
        if port_value is not None:
            ports = _normalise_ports([port_value])
        else:
            ports = DEFAULT_PORTS

    public_base_value = section.get("public_base")
    public_base = str(public_base_value).strip() if public_base_value else None

    config = PortsConfig(host=host, ports=ports, public_base=public_base)
    return _apply_env_overrides(config)


def get_config() -> dict[str, object]:
    """
    Return the canonical port configuration with environment overrides applied.
    """
    cfg = _derive_config()
    return cfg.to_dict()


def _config_stamp(payload: Mapping[str, object]) -> str:
    serialised = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def stamp() -> str:
    """
    Compute a hash stamp for the current configuration.
    """
    return _config_stamp(get_config())


def _write_config(payload: Mapping[str, object]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = _load_raw_config()
    current["server"] = dict(payload)
    CONFIG_PATH.write_text(
        json.dumps(current, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_runtime(payload: Mapping[str, object]) -> None:
    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data["stamp"] = _config_stamp(payload.get("config") or payload)
    data["updated"] = time.time()
    RUNTIME_FILE.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def set_config(
    host: str, ports: Sequence[int], public_base: str | None
) -> dict[str, object]:
    """
    Persist the supplied configuration to disk and update runtime metadata.
    """
    cfg = PortsConfig(
        host=host.strip() or DEFAULT_HOST,
        ports=_normalise_ports(ports),
        public_base=(public_base.strip() if public_base else None),
    )
    payload = cfg.to_dict()
    _write_config(payload)
    runtime_payload = {
        "config": payload,
        "active": None,
        "base_url": payload.get("public_base") or None,
    }
    _write_runtime(runtime_payload)
    return payload


def record_runtime_state(
    *,
    host: str,
    ports: Sequence[int],
    active_port: int | None,
    base_url: str | None,
    public_base: str | None,
) -> None:
    """
    Update the runtime file with the currently bound server state.
    """
    config_payload = {
        "host": host,
        "ports": list(ports),
        "public_base": public_base,
    }
    runtime_payload = {
        "config": config_payload,
        "active": active_port,
        "base_url": base_url,
    }
    _write_runtime(runtime_payload)


__all__ = [
    "get_config",
    "record_runtime_state",
    "set_config",
    "stamp",
]
