"""Headless bootstrap helpers for on-demand dependency installation."""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import urlsplit

_LOG_PREFIX = "[ComfyVN]"
_SKIP_VALUES = {"0", "false", "no"}


def _repo_root() -> Path:
    path = Path(__file__).resolve()
    try:
        return path.parents[3]
    except IndexError:
        return path.parent


def _auto_install_enabled() -> bool:
    value = os.getenv("COMFYVN_HEADLESS_AUTO", "1")
    return value.strip().lower() not in _SKIP_VALUES


def _candidate_requirements(root: Path) -> Iterable[Path]:
    yield root / "requirements-headless.txt"
    yield root / "requirements" / "web.txt"
    yield root / "requirements" / "requirements-headless.txt"


def _select_requirements(root: Path) -> Optional[Path]:
    for candidate in _candidate_requirements(root):
        if candidate.is_file():
            return candidate
    return None


def _default_index_url() -> str:
    return "https://pypi.org/simple/"


def _index_target() -> Tuple[Optional[str], Optional[int]]:
    raw = os.getenv("PIP_INDEX_URL") or _default_index_url()
    try:
        parsed = urlsplit(raw)
    except Exception:
        return None, None
    host = parsed.hostname
    if not host:
        return None, None
    port = parsed.port
    if port is None:
        if parsed.scheme == "https":
            port = 443
        elif parsed.scheme == "http":
            port = 80
    return host, port


def _network_available() -> Tuple[bool, str]:
    no_index = os.getenv("PIP_NO_INDEX", "").strip().lower() in {"1", "true", "yes"}
    if no_index:
        return True, ""
    host, port = _index_target()
    if not host:
        return True, ""
    try:
        with socket.create_connection((host, port), timeout=3):
            return True, ""
    except OSError as exc:
        port_display = f":{port}" if port else ""
        return False, f"{host}{port_display} unreachable ({exc})"


def _append_log(log_path: Path, message: str) -> None:
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def ensure_headless_ready() -> None:
    """Install headless-specific dependencies when the requirements hash changes."""
    if not _auto_install_enabled():
        return

    root = _repo_root()
    requirements_path = _select_requirements(root)
    if requirements_path is None:
        return

    runtime_dir = root / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    stamp_file = runtime_dir / "headless.hash"
    log_file = runtime_dir / "headless_install.log"

    digest = hashlib.sha256(requirements_path.read_bytes()).hexdigest()
    if stamp_file.exists() and stamp_file.read_text().strip() == digest:
        return

    available, reason = _network_available()
    display = _display_path(requirements_path, root)
    if not available:
        message = (
            f"Headless auto-install skipped (offline: {reason}). "
            "Install dependencies manually when connectivity is restored."
        )
        print(f"{_LOG_PREFIX} {message}")
        _append_log(log_file, message)
        return

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-r",
        str(requirements_path),
        "-q",
    ]
    try:
        with log_file.open("a", encoding="utf-8") as stream:
            timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            stream.write(
                f"{timestamp} Installing headless requirements from {display}\n"
            )
            stream.flush()
            subprocess.run(
                command,
                check=True,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
            success_stamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            stream.write(f"{success_stamp} Install succeeded for {display}\n")
    except Exception as exc:
        failure_message = (
            f"Headless dependency install failed for {display}; "
            f"see {_display_path(log_file, root)} for details."
        )
        print(f"{_LOG_PREFIX} {failure_message}")
        _append_log(log_file, f"Install failure: {exc}")
        return

    stamp_file.write_text(digest)
    print(
        f"{_LOG_PREFIX} Headless dependencies installed from {display}.",
    )
