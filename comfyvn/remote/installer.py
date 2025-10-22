"""
Remote installer orchestrator.

The orchestrator exposes a small module registry describing how to provision
common ComfyVN companion services (ComfyUI, SillyTavern, LM Studio, Ollama)
on SSH-accessible hosts.  Consumers call :func:`plan` to derive the action
sequence for a host and then :func:`apply` to materialise the plan while
recording status and log output.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, MutableMapping, Optional

LOGGER = logging.getLogger(__name__)

# Environment overrides keep tests isolated while letting production default
# to repo-relative paths.
_STATUS_ENV = "COMFYVN_REMOTE_INSTALL_STATUS_ROOT"
_LOG_ENV = "COMFYVN_REMOTE_INSTALL_LOG_ROOT"


def _status_root() -> Path:
    raw = os.getenv(_STATUS_ENV)
    base = Path(raw).expanduser() if raw else Path("data/remote/install")
    return base.resolve()


def _log_root() -> Path:
    raw = os.getenv(_LOG_ENV)
    base = Path(raw).expanduser() if raw else Path("logs/remote/install")
    return base.resolve()


def _timestamp() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _safe_host_token(host: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", host.strip())
    return token or "remote"


def _status_path(host: str) -> Path:
    return (_status_root() / f"{_safe_host_token(host)}.json").resolve()


def _log_path(host: str) -> Path:
    return (_log_root() / f"{_safe_host_token(host)}.log").resolve()


def _load_status(host: str) -> dict:
    path = _status_path(host)
    if not path.exists():
        return {"host": host, "modules": {}, "version": 1}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed to read status file %s: %s", path, exc)
        return {"host": host, "modules": {}, "version": 1}
    modules = data.get("modules")
    if not isinstance(modules, dict):
        data["modules"] = {}
    data.setdefault("host", host)
    data.setdefault("version", 1)
    return data


def _save_status(host: str, data: MutableMapping[str, object]) -> Path:
    path = _status_path(host)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["host"] = host
    data["updated_at"] = _timestamp()
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(payload, encoding="utf-8")
    return path


def open_log(host: str) -> tuple[Callable[[str], None], Path]:
    """
    Return a log writer function and the associated file path for *host*.

    The writer appends timestamped lines to the log file, creating parent
    directories as needed.
    """

    path = _log_path(host)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write(message: str) -> None:
        line = f"[{_timestamp()}] {message}"
        with path.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")

    return _write, path


def status_path(host: str) -> Path:
    """
    Return the resolved status path for *host* without writing any data.
    """

    path = _status_path(host)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    name: str
    install_steps: List[Dict[str, object]]
    config_sync: List[Dict[str, object]] = field(default_factory=list)
    notes: str = ""
    tags: List[str] = field(default_factory=list)


def _registry() -> Dict[str, ModuleSpec]:
    return {
        "comfyui": ModuleSpec(
            key="comfyui",
            name="ComfyUI",
            install_steps=[
                {
                    "type": "command",
                    "command": "sudo apt-get update",
                    "description": "Refresh package index.",
                },
                {
                    "type": "command",
                    "command": "sudo apt-get install -y git python3-venv python3-pip",
                    "description": "Ensure Python tooling required by ComfyUI.",
                },
                {
                    "type": "command",
                    "command": "git clone https://github.com/comfyanonymous/ComfyUI.git ~/ComfyUI",
                    "description": "Clone upstream ComfyUI repository.",
                },
                {
                    "type": "command",
                    "command": "cd ~/ComfyUI && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt",
                    "description": "Create virtualenv and install dependencies.",
                },
            ],
            config_sync=[
                {
                    "type": "sync",
                    "source": "config/comfyvn.json",
                    "destination": "~/.config/comfyvn/remote/comfyui.json",
                    "description": "Mirror ComfyVN core config for the remote ComfyUI host.",
                }
            ],
            notes="Installs ComfyUI core server and prepares a mirrored configuration stub.",
            tags=["ssh", "python", "workflow"],
        ),
        "sillytavern": ModuleSpec(
            key="sillytavern",
            name="SillyTavern",
            install_steps=[
                {
                    "type": "command",
                    "command": "git clone https://github.com/SillyTavern/SillyTavern.git ~/SillyTavern",
                    "description": "Clone SillyTavern repository.",
                },
                {
                    "type": "command",
                    "command": "cd ~/SillyTavern && npm install",
                    "description": "Install SillyTavern dependencies.",
                },
            ],
            config_sync=[
                {
                    "type": "sync",
                    "source": "SillyTavern Extension",
                    "destination": "~/SillyTavern/extensions/comfyvn",
                    "description": "Sync bundled ComfyVN SillyTavern extension assets.",
                    "optional": True,
                }
            ],
            notes="Deploys SillyTavern with the ComfyVN extension payload when available.",
            tags=["ssh", "node", "roleplay"],
        ),
        "lmstudio": ModuleSpec(
            key="lmstudio",
            name="LM Studio",
            install_steps=[
                {
                    "type": "command",
                    "command": "mkdir -p ~/lmstudio && curl -L https://releases.lmstudio.ai/linux/latest -o ~/lmstudio/LMStudio.tar.gz",
                    "description": "Download latest LM Studio archive.",
                },
                {
                    "type": "command",
                    "command": "cd ~/lmstudio && tar -xzf LMStudio.tar.gz",
                    "description": "Extract LM Studio bundle.",
                },
            ],
            config_sync=[
                {
                    "type": "sync",
                    "source": "config/settings/config.json",
                    "destination": "~/.config/LMStudio/settings.json",
                    "description": "Mirror ComfyVN model registry hints into LM Studio preferences.",
                    "optional": True,
                }
            ],
            notes="Stage LM Studio binaries and align settings with ComfyVN expectations.",
            tags=["ssh", "llm", "openai-compatible"],
        ),
        "ollama": ModuleSpec(
            key="ollama",
            name="Ollama",
            install_steps=[
                {
                    "type": "command",
                    "command": "curl https://ollama.ai/install.sh | sh",
                    "description": "Install Ollama using official script.",
                },
                {
                    "type": "command",
                    "command": "ollama serve",
                    "description": "Prime Ollama service (first launch).",
                },
            ],
            config_sync=[
                {
                    "type": "sync",
                    "source": "config/settings/config.json",
                    "destination": "~/.ollama/config.json",
                    "description": "Push shared model registry settings.",
                    "optional": True,
                }
            ],
            notes="Installs Ollama runtime and seeds shared model registry metadata.",
            tags=["ssh", "llm", "registry"],
        ),
    }


def list_modules() -> List[dict]:
    """Return serialisable view of the module registry."""
    modules = []
    for key, spec in _registry().items():
        modules.append(
            {
                "id": key,
                "name": spec.name,
                "notes": spec.notes,
                "tags": list(spec.tags),
                "install_steps": list(spec.install_steps),
                "config_sync": list(spec.config_sync),
            }
        )
    return modules


def _normalize_modules(modules: Iterable[str]) -> List[str]:
    normalised: List[str] = []
    seen: set[str] = set()
    for module in modules:
        key = str(module).strip().lower()
        if not key or key in seen:
            continue
        if key not in _registry():
            raise KeyError(key)
        normalised.append(key)
        seen.add(key)
    return normalised


def plan(host: str, modules: Iterable[str]) -> List[dict]:
    """
    Build an action plan for the given *host* and module identifiers.

    Each plan entry contains the effective action (`install` or `noop`), the
    module metadata, and the command/configuration steps that would run.  The
    planner honours the status file, skipping modules that were already marked
    as installed.
    """

    host = str(host or "").strip()
    if not host:
        raise ValueError("host is required")

    module_keys = _normalize_modules(modules)
    status = _load_status(host)
    installed = {
        key
        for key, meta in (status.get("modules") or {}).items()
        if isinstance(meta, dict) and meta.get("state") == "installed"
    }

    results: List[dict] = []
    registry = _registry()
    for key in module_keys:
        spec = registry[key]
        if key in installed:
            results.append(
                {
                    "host": host,
                    "module": key,
                    "name": spec.name,
                    "action": "noop",
                    "reason": "already installed",
                    "notes": spec.notes,
                    "tags": list(spec.tags),
                }
            )
            continue
        results.append(
            {
                "host": host,
                "module": key,
                "name": spec.name,
                "action": "install",
                "steps": list(spec.install_steps),
                "config_sync": list(spec.config_sync),
                "notes": spec.notes,
                "tags": list(spec.tags),
            }
        )
    return results


def apply(
    host: str,
    plan_entries: Iterable[dict],
    *,
    log_hook: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Execute the supplied plan entries for *host*.

    The installer operates in a dry fashion: it records the requested steps to
    the log, marks modules as installed in the status file, and surfaces a
    summary without performing remote execution itself.  This keeps automated
    tests deterministic while still producing an audit trail that external
    runners can replay.
    """

    host = str(host or "").strip()
    if not host:
        raise ValueError("host is required")

    plan_list = [dict(entry) for entry in plan_entries]

    writer = log_hook
    if writer is None:
        writer, log_path = open_log(host)
    else:
        log_path = _log_path(host)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    writer(f"Starting remote install orchestration for host={host}")

    status = _load_status(host)
    modules_meta = status.setdefault("modules", {})
    installed: List[str] = []
    skipped: List[str] = []

    registry = _registry()

    for entry in plan_list:
        module_key = str(entry.get("module") or "").strip().lower()
        if not module_key:
            skipped.append(module_key or "?")
            continue
        spec = registry.get(module_key)
        if spec is None:
            writer(f"Skipping unknown module '{module_key}'")
            skipped.append(module_key)
            continue

        action = entry.get("action")
        if action != "install":
            writer(f"[{module_key}] no-op ({entry.get('reason', 'no action needed')})")
            skipped.append(module_key)
            modules_meta.setdefault(module_key, {}).update(
                {
                    "state": (
                        "installed"
                        if modules_meta.get(module_key, {}).get("state") == "installed"
                        else "skipped"
                    ),
                    "notes": spec.notes,
                }
            )
            continue

        writer(f"[{module_key}] install begin → {spec.name}")
        for step in entry.get("steps") or []:
            desc = step.get("description") or step.get("command")
            writer(f"[{module_key}] step: {desc}")
        for sync in entry.get("config_sync") or []:
            src = sync.get("source")
            dest = sync.get("destination")
            description = sync.get("description") or f"{src} -> {dest}"
            source_path = Path(src) if src else None
            optional = bool(sync.get("optional"))
            if source_path and source_path.exists():
                writer(f"[{module_key}] sync: {description} (source ok: {source_path})")
            elif optional:
                writer(f"[{module_key}] sync: {description} (source missing, optional)")
            else:
                writer(
                    f"[{module_key}] sync: {description} (source missing, mark pending)"
                )
        modules_meta[module_key] = {
            "state": "installed",
            "installed_at": _timestamp(),
            "notes": spec.notes,
            "tags": list(spec.tags),
        }
        installed.append(module_key)
        writer(f"[{module_key}] install marked complete (dry-run)")

    status_path = _save_status(host, status)
    writer(f"Install orchestration complete. status_path={status_path}")

    return {
        "host": host,
        "installed": installed,
        "skipped": skipped,
        "log_path": str(log_path),
        "status_path": str(status_path),
        "plan": plan_list,
        "registry": list_modules(),
        "status": "noop" if not installed else "installed",
    }


__all__ = [
    "ModuleSpec",
    "apply",
    "list_modules",
    "open_log",
    "plan",
    "status_path",
]
