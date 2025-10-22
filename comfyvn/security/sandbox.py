from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence, Tuple
from urllib.parse import urlparse

LOGGER = logging.getLogger(__name__)
AUDIT_LOGGER = logging.getLogger("comfyvn.security.sandbox")

_ORIGINAL_SOCKET = socket.socket
_ORIGINAL_CREATE_CONNECTION = socket.create_connection

_ACTIVE_GUARD: Optional["NetworkGuard"] = None
_HOOK_SANDBOX_BLOCKED = "on_sandbox_network_blocked"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class NetworkRule:
    host_pattern: str
    port: Optional[int]

    def matches(self, host: str, port: Optional[int]) -> bool:
        host = host.lower()
        if self.port is not None and port != self.port:
            return False
        pattern = self.host_pattern
        if pattern == "*":
            return True
        if pattern.startswith("*."):
            suffix = pattern[1:]
            return host.endswith(suffix)
        if pattern == "localhost":
            return host in {"localhost", "127.0.0.1", "::1"}
        return host == pattern


def _parse_host_port(raw: str) -> Tuple[str, Optional[int]]:
    item = raw.strip()
    if not item:
        raise ValueError("empty rule")

    if "://" in item:
        parsed = urlparse(item)
        host = parsed.hostname
        port = parsed.port
    elif item.startswith("["):
        closing = item.find("]")
        if closing == -1:
            raise ValueError(f"invalid IPv6 rule: {raw!r}")
        host = item[1:closing]
        remainder = item[closing + 1 :]
        port = None
        if remainder.startswith(":"):
            port = int(remainder[1:])
    else:
        if item.count(":") == 0:
            host = item
            port = None
        else:
            host_part, port_part = item.rsplit(":", 1)
            if not host_part or not port_part:
                host = item
                port = None
            else:
                host = host_part
                port = int(port_part)

    if host is None or not str(host).strip():
        raise ValueError(f"invalid network rule: {raw!r}")
    host = str(host).strip().lower()
    if port is not None:
        if port < 0 or port > 65535:
            raise ValueError(f"invalid port in rule: {raw!r}")
    return host, port


def parse_network_rule(rule: str) -> NetworkRule:
    host, port = _parse_host_port(rule)
    return NetworkRule(host_pattern=host, port=port)


class NetworkGuard:
    def __init__(self, rules: Sequence[str] | Iterable[str]):
        self.rules = []
        for entry in rules:
            try:
                parsed = parse_network_rule(str(entry))
                self.rules.append(parsed)
            except Exception as exc:
                LOGGER.warning("Ignoring invalid network allow rule %r: %s", entry, exc)

    def allowed(self, host: Optional[str], port: Optional[int]) -> bool:
        if host is None:
            return False
        if not self.rules:
            return False
        host = host.lower()
        for rule in self.rules:
            if rule.matches(host, port):
                return True
        return False


def _normalize_address(address) -> Tuple[Optional[str], Optional[int]]:
    if isinstance(address, tuple):
        if not address:
            return None, None
        host = address[0]
        port = address[1] if len(address) > 1 else None
        if isinstance(port, tuple):
            port = port[0]
        try:
            port = int(port) if port is not None else None
        except (TypeError, ValueError):
            port = None
        return str(host) if host is not None else None, port
    if isinstance(address, str):
        # Unix domain sockets or named pipes; treat as blocked.
        return address, None
    return None, None


def _deny(host: Optional[str], port: Optional[int]) -> None:
    payload = {
        "event": "sandbox.network.blocked",
        "host": str(host) if host else None,
        "port": port,
        "timestamp": _utc_timestamp(),
    }
    AUDIT_LOGGER.info(json.dumps(payload))
    try:
        from comfyvn.core import modder_hooks
    except Exception:
        pass
    else:
        sanitized = {k: v for k, v in payload.items() if k != "event"}
        try:
            modder_hooks.emit(_HOOK_SANDBOX_BLOCKED, sanitized)
        except Exception:
            LOGGER.debug(
                "Failed to emit sandbox modder hook %s",
                _HOOK_SANDBOX_BLOCKED,
                exc_info=True,
            )
    raise RuntimeError(f"network blocked by sandbox (host={host!r}, port={port!r})")


class GuardedSocket(_ORIGINAL_SOCKET):
    def connect(self, address):
        host, port = _normalize_address(address)
        if _ACTIVE_GUARD and not _ACTIVE_GUARD.allowed(host, port):
            _deny(host, port)
        return super().connect(address)

    def connect_ex(self, address):
        host, port = _normalize_address(address)
        if _ACTIVE_GUARD and not _ACTIVE_GUARD.allowed(host, port):
            _deny(host, port)
        return super().connect_ex(address)


def _guarded_create_connection(address, *args, **kwargs):
    host, port = _normalize_address(address)
    if _ACTIVE_GUARD and not _ACTIVE_GUARD.allowed(host, port):
        _deny(host, port)
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def apply_network_policy(
    enabled: bool,
    allow_rules: Sequence[str] | Iterable[str] | None = None,
) -> None:
    """
    Patch socket primitives so only allow-listed hosts are reachable.

    When *enabled* is ``False`` every outbound attempt is blocked.  When
    *enabled* is ``True`` the provided *allow_rules* control which hosts (and
    optional ports) may be reached.  Rules accept bare hostnames, ``host:port``
    pairs, IPv6 literals (``[::1]:8080``), or full URLs (``https://...``).
    """

    global _ACTIVE_GUARD
    if not enabled:
        _ACTIVE_GUARD = NetworkGuard([])
    else:
        _ACTIVE_GUARD = NetworkGuard(allow_rules or [])
    socket.socket = GuardedSocket  # type: ignore[assignment]
    socket.create_connection = _guarded_create_connection  # type: ignore[assignment]


__all__ = [
    "NetworkGuard",
    "NetworkRule",
    "apply_network_policy",
    "parse_network_rule",
]
