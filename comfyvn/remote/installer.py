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
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
)

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
    detect_steps: List[Dict[str, object]] = field(default_factory=list)
    notes: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass(slots=True)
class SSHConfig:
    host: str
    user: Optional[str] = None
    port: Optional[int] = None
    identity: Optional[Path] = None
    ssh_command: str = "ssh"
    scp_command: str = "scp"
    connect_timeout: float = 10.0
    env: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, host: str, payload: Mapping[str, Any]) -> "SSHConfig":
        data = dict(payload)
        user = data.get("user") or data.get("username")
        port = data.get("port")
        identity = data.get("identity") or data.get("identity_file")
        ssh_cmd = data.get("ssh_command") or "ssh"
        scp_cmd = data.get("scp_command") or "scp"
        timeout = data.get("connect_timeout") or data.get("timeout")
        env_payload = data.get("env") or {}

        try:
            port_value = int(port) if port is not None else None
        except (TypeError, ValueError) as exc:  # pragma: no cover - validation
            raise RuntimeError("SSH port must be an integer") from exc

        identity_path: Optional[Path] = None
        if identity:
            identity_path = Path(str(identity)).expanduser().resolve()

        try:
            timeout_value = float(timeout) if timeout is not None else 10.0
        except (TypeError, ValueError) as exc:  # pragma: no cover - validation
            raise RuntimeError("SSH timeout must be numeric") from exc

        env_map: Dict[str, str] = {}
        if isinstance(env_payload, Mapping):
            for key, value in env_payload.items():
                if value is None:
                    continue
                env_map[str(key)] = str(value)

        return cls(
            host=host,
            user=str(user) if user else None,
            port=port_value,
            identity=identity_path,
            ssh_command=str(ssh_cmd),
            scp_command=str(scp_cmd),
            connect_timeout=timeout_value,
            env=env_map,
        )


class RuntimeConfigurationError(RuntimeError):
    """Raised when remote installer runtime cannot be configured."""


class RemoteInstallError(RuntimeError):
    """Raised when a remote install step fails."""


class InstallRuntime:
    """Runtime helper for probing and applying remote installer steps."""

    def __init__(
        self,
        ssh: Optional[SSHConfig],
        *,
        enable_probe: bool = True,
        record_only: bool = False,
    ) -> None:
        self.ssh = ssh
        self.enable_probe = bool(enable_probe and ssh)
        self.record_only = bool(record_only)
        self._bridge = None

    # ----------------------------------------------------------------- bridge
    def _get_bridge(self):
        if not self.ssh:
            raise RemoteInstallError("SSH configuration missing")
        if self._bridge is None:
            from comfyvn.bridge.remote import RemoteBridge

            self._bridge = RemoteBridge(
                host=self.ssh.host,
                user=self.ssh.user,
                port=self.ssh.port,
                identity_file=self.ssh.identity,
                ssh_command=self.ssh.ssh_command,
                scp_command=self.ssh.scp_command,
                connect_timeout=self.ssh.connect_timeout,
                env=self.ssh.env or None,
            )
        return self._bridge

    # ----------------------------------------------------------------- probing
    def probe_installed(self, module: str, spec: ModuleSpec) -> Optional[bool]:
        if not self.enable_probe or not self.ssh:
            return None
        if not spec.detect_steps:
            return None

        bridge = self._get_bridge()
        for check in spec.detect_steps:
            if check.get("type") != "command":
                continue
            command = str(check.get("command") or "").strip()
            if not command:
                continue
            timeout = float(check.get("timeout") or 20.0)
            try:
                proc = bridge.run(command, check=False, timeout=timeout)
            except Exception as exc:  # pragma: no cover - remote failure paths
                LOGGER.debug(
                    "Remote detection failed for module=%s command=%s: %s",
                    module,
                    command,
                    exc,
                )
                return None
            if proc.returncode != 0:
                LOGGER.debug(
                    "Remote detection negative for module=%s command=%s rc=%s",
                    module,
                    command,
                    proc.returncode,
                )
                return False
        return True

    # ---------------------------------------------------------------- execution
    def run_step(
        self, module: str, step: Mapping[str, Any], writer: Callable[[str], None]
    ):
        desc = step.get("description") or step.get("command") or "remote step"
        writer(f"[{module}] step: {desc}")
        if self.record_only or not self.ssh:
            writer(f"[{module}] step skipped (record-only mode)")
            return
        if step.get("type") != "command":
            writer(f"[{module}] unsupported step type={step.get('type')}, skip")
            return

        command = str(step.get("command") or "").strip()
        if not command:
            raise RemoteInstallError(f"{module} command missing")
        timeout = float(step.get("timeout") or 600.0)
        bridge = self._get_bridge()
        try:
            proc = bridge.run(command, check=False, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RemoteInstallError(f"{module} command timed out: {desc}") from exc
        except Exception as exc:  # pragma: no cover - environment specific
            raise RemoteInstallError(f"{module} command failed: {desc}") from exc
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            raise RemoteInstallError(
                f"{module} command rc={proc.returncode}: {desc}{' :: ' + stderr if stderr else ''}"
            )

    def sync_payload(
        self,
        module: str,
        sync: Mapping[str, Any],
        writer: Callable[[str], None],
    ) -> None:
        src = sync.get("source")
        dest = sync.get("destination")
        description = sync.get("description") or f"{src} -> {dest}"
        optional = bool(sync.get("optional"))

        source_path = Path(str(src)) if src else None
        if not source_path or not source_path.exists():
            status = "optional" if optional else "missing"
            writer(
                f"[{module}] sync: {description} (source {status}{' - skipped' if optional else ''})"
            )
            if optional:
                return
            raise RemoteInstallError(
                f"{module} config sync missing source: {source_path}"
            )

        writer(f"[{module}] sync: {description}")
        if self.record_only or not self.ssh:
            writer(f"[{module}] sync skipped (record-only mode)")
            return
        if not dest:
            raise RemoteInstallError(f"{module} config sync missing destination")

        bridge = self._get_bridge()
        dest_parent = os.path.dirname(str(dest)) or "~"
        mkdir_cmd = f"mkdir -p {shlex.quote(dest_parent)}"
        bridge.run(mkdir_cmd, check=False, timeout=30.0)
        exists_cmd = f"test -e {shlex.quote(str(dest))}"
        proc = bridge.run(exists_cmd, check=False, timeout=15.0)
        if proc.returncode == 0:
            writer(f"[{module}] sync destination exists, skip to avoid overwrite")
            return

        recursive = source_path.is_dir()
        try:
            bridge.push(source_path, dest, recursive=recursive)
        except Exception as exc:  # pragma: no cover - scp failures depend on env
            raise RemoteInstallError(f"{module} failed to push {description}") from exc
        writer(f"[{module}] sync complete → {dest}")


def build_runtime(
    host: str,
    ssh_payload: Optional[Mapping[str, Any]],
    *,
    enable_probe: bool = True,
    record_only: bool = False,
) -> Optional[InstallRuntime]:
    if not ssh_payload:
        return None
    try:
        config = SSHConfig.from_mapping(host, ssh_payload)
    except Exception as exc:
        raise RuntimeConfigurationError(str(exc)) from exc
    return InstallRuntime(config, enable_probe=enable_probe, record_only=record_only)


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
                    "command": (
                        "if [ -d ~/ComfyUI/.git ]; then "
                        "cd ~/ComfyUI && git fetch --all --tags && git pull --ff-only; "
                        "else git clone https://github.com/comfyanonymous/ComfyUI.git ~/ComfyUI; fi"
                    ),
                    "description": "Clone or fast-forward the ComfyUI repository.",
                },
                {
                    "type": "command",
                    "command": (
                        "cd ~/ComfyUI && python3 -m venv venv && "
                        "source venv/bin/activate && pip install --upgrade -r requirements.txt"
                    ),
                    "description": "Create virtualenv and install dependencies.",
                },
                {
                    "type": "command",
                    "command": (
                        "mkdir -p ~/.config/comfyvn/remote && "
                        "touch ~/.config/comfyvn/remote/comfyui.installed"
                    ),
                    "description": "Record ComfyUI installation sentinel.",
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
            detect_steps=[
                {
                    "type": "command",
                    "command": "test -d ~/ComfyUI",
                    "description": "Check ComfyUI repository exists.",
                },
                {
                    "type": "command",
                    "command": "test -f ~/.config/comfyvn/remote/comfyui.installed",
                    "description": "Check ComfyUI sentinel file.",
                },
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
                    "command": (
                        "if [ -d ~/SillyTavern/.git ]; then "
                        "cd ~/SillyTavern && git fetch --all --tags && git pull --ff-only; "
                        "else git clone https://github.com/SillyTavern/SillyTavern.git ~/SillyTavern; fi"
                    ),
                    "description": "Clone or update SillyTavern repository.",
                },
                {
                    "type": "command",
                    "command": "cd ~/SillyTavern && npm install",
                    "description": "Install SillyTavern dependencies.",
                },
                {
                    "type": "command",
                    "command": (
                        "mkdir -p ~/.config/comfyvn/remote && "
                        "touch ~/.config/comfyvn/remote/sillytavern.installed"
                    ),
                    "description": "Record SillyTavern installation sentinel.",
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
            detect_steps=[
                {
                    "type": "command",
                    "command": "test -d ~/SillyTavern",
                    "description": "Check SillyTavern repository exists.",
                },
                {
                    "type": "command",
                    "command": "test -f ~/.config/comfyvn/remote/sillytavern.installed",
                    "description": "Check SillyTavern sentinel file.",
                },
            ],
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
                {
                    "type": "command",
                    "command": (
                        "mkdir -p ~/.config/comfyvn/remote && "
                        "touch ~/.config/comfyvn/remote/lmstudio.installed"
                    ),
                    "description": "Record LM Studio installation sentinel.",
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
            detect_steps=[
                {
                    "type": "command",
                    "command": "test -d ~/lmstudio",
                    "description": "Check LM Studio directory exists.",
                },
                {
                    "type": "command",
                    "command": "test -f ~/.config/comfyvn/remote/lmstudio.installed",
                    "description": "Check LM Studio sentinel file.",
                },
            ],
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
                {
                    "type": "command",
                    "command": (
                        "mkdir -p ~/.config/comfyvn/remote && "
                        "touch ~/.config/comfyvn/remote/ollama.installed"
                    ),
                    "description": "Record Ollama installation sentinel.",
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
            detect_steps=[
                {
                    "type": "command",
                    "command": "command -v ollama",
                    "description": "Check Ollama binary on PATH.",
                },
                {
                    "type": "command",
                    "command": "test -f ~/.config/comfyvn/remote/ollama.installed",
                    "description": "Check Ollama sentinel file.",
                },
            ],
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
                "detect_steps": list(spec.detect_steps),
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


def plan(
    host: str,
    modules: Iterable[str],
    *,
    runtime: Optional[InstallRuntime] = None,
) -> List[dict]:
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

    detection_state: Dict[str, Optional[bool]] = {}

    results: List[dict] = []
    registry = _registry()
    for key in module_keys:
        spec = registry[key]
        detected = runtime.probe_installed(key, spec) if runtime else None
        detection_state[key] = detected
        if detected:
            installed.add(key)
            reason = "detected installed on remote host"
        else:
            reason = "already installed"
        if key in installed:
            results.append(
                {
                    "host": host,
                    "module": key,
                    "name": spec.name,
                    "action": "noop",
                    "reason": reason,
                    "notes": spec.notes,
                    "tags": list(spec.tags),
                    "detected": bool(detected),
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
                "detected": detected if detected is not None else False,
            }
        )
    return results


def apply(
    host: str,
    plan_entries: Iterable[dict],
    *,
    log_hook: Optional[Callable[[str], None]] = None,
    runtime: Optional[InstallRuntime] = None,
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
    failed: List[str] = []

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
            reason = entry.get("reason", "no action needed")
            writer(f"[{module_key}] no-op ({reason})")
            skipped.append(module_key)
            detected = entry.get("detected")
            current_state = modules_meta.get(module_key, {}).get("state")
            new_state = (
                "installed" if detected or current_state == "installed" else "skipped"
            )
            modules_meta.setdefault(module_key, {}).update(
                {
                    "state": new_state,
                    "notes": spec.notes,
                    "tags": list(spec.tags),
                    "reason": reason,
                    "detected": bool(detected),
                }
            )
            continue

        writer(f"[{module_key}] install begin → {spec.name}")
        module_error: Optional[str] = None

        for step in entry.get("steps") or []:
            try:
                if runtime:
                    runtime.run_step(module_key, step, writer)
                else:
                    desc = step.get("description") or step.get("command")
                    writer(f"[{module_key}] step: {desc}")
            except RemoteInstallError as exc:
                module_error = str(exc)
                break

        if module_error is None:
            for sync in entry.get("config_sync") or []:
                try:
                    if runtime:
                        runtime.sync_payload(module_key, sync, writer)
                    else:
                        src = sync.get("source")
                        dest = sync.get("destination")
                        description = sync.get("description") or f"{src} -> {dest}"
                        source_path = Path(src) if src else None
                        optional = bool(sync.get("optional"))
                        if source_path and source_path.exists():
                            writer(
                                f"[{module_key}] sync: {description} (source ok: {source_path})"
                            )
                        elif optional:
                            writer(
                                f"[{module_key}] sync: {description} (source missing, optional)"
                            )
                        else:
                            module_error = f"config sync missing source ({description})"
                            writer(
                                f"[{module_key}] sync: {description} (source missing, abort)"
                            )
                            break
                except RemoteInstallError as exc:
                    module_error = str(exc)
                    break

        if module_error:
            failed.append(module_key)
            modules_meta[module_key] = {
                "state": "failed",
                "failed_at": _timestamp(),
                "notes": spec.notes,
                "tags": list(spec.tags),
                "error": module_error,
            }
            writer(f"[{module_key}] install failed: {module_error}")
            continue

        modules_meta[module_key] = {
            "state": "installed",
            "installed_at": _timestamp(),
            "notes": spec.notes,
            "tags": list(spec.tags),
        }
        installed.append(module_key)
        writer(f"[{module_key}] install marked complete")

    status_path = _save_status(host, status)
    writer(f"Install orchestration complete. status_path={status_path}")

    return {
        "host": host,
        "installed": installed,
        "skipped": skipped,
        "failed": failed,
        "log_path": str(log_path),
        "status_path": str(status_path),
        "plan": plan_list,
        "registry": list_modules(),
        "status": "failed" if failed else ("noop" if not installed else "installed"),
    }


def read_status(host: str) -> Dict[str, Any]:
    host_str = str(host or "").strip()
    if not host_str:
        raise ValueError("host is required")
    return _load_status(host_str)


def list_statuses() -> List[Dict[str, Any]]:
    root = _status_root()
    entries: List[Dict[str, Any]] = []
    if not root.exists():
        return entries
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - defensive against manual edits
            continue
        host = str(payload.get("host") or path.stem)
        modules = {}
        for key, meta in (payload.get("modules") or {}).items():
            if isinstance(meta, Mapping):
                modules[key] = meta.get("state")
        entries.append(
            {
                "host": host,
                "modules": modules,
                "updated_at": payload.get("updated_at"),
                "status_path": str(path),
            }
        )
    return entries


__all__ = [
    "InstallRuntime",
    "ModuleSpec",
    "RemoteInstallError",
    "RuntimeConfigurationError",
    "SSHConfig",
    "apply",
    "build_runtime",
    "list_modules",
    "list_statuses",
    "open_log",
    "plan",
    "read_status",
    "status_path",
]
