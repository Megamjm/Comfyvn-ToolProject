from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from comfyvn.bridge.remote import RemoteBridge, RemoteCapabilityReport
from comfyvn.core import compute_providers as generic_providers

LOGGER = logging.getLogger(__name__)


def _coerce_path(value: Any) -> Optional[Path]:
    if not value:
        return None
    try:
        return Path(str(value)).expanduser()
    except Exception:  # pragma: no cover - defensive
        return None


@dataclass(slots=True)
class SSHConfig:
    host: str = ""
    user: str = "root"
    port: int = 22
    identity_file: Optional[Path] = None
    ssh_command: str = "ssh"
    scp_command: str = "scp"


def _extract_ssh_config(provider: Dict[str, Any]) -> SSHConfig:
    config = provider.get("config") or {}
    ssh_raw = config.get("ssh") or config.get("ssh_config") or config

    host = (
        ssh_raw.get("host")
        or ssh_raw.get("hostname")
        or provider.get("host")
        or provider.get("base_host")
        or ""
    )
    user = ssh_raw.get("user") or ssh_raw.get("username") or "root"
    port_raw = ssh_raw.get("port") or 22
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 22

    identity = (
        ssh_raw.get("identity_file")
        or ssh_raw.get("identity")
        or ssh_raw.get("key")
        or ssh_raw.get("keyfile")
        or ssh_raw.get("ssh_key")
    )
    identity_path = _coerce_path(identity)
    ssh_cmd = ssh_raw.get("ssh_command") or "ssh"
    scp_cmd = ssh_raw.get("scp_command") or "scp"

    return SSHConfig(
        host=str(host),
        user=str(user),
        port=port,
        identity_file=identity_path,
        ssh_command=str(ssh_cmd),
        scp_command=str(scp_cmd),
    )


def _artifact_summary(paths: List[Path]) -> List[str]:
    return [str(path) for path in paths]


@dataclass(slots=True)
class UnraidAdapter:
    provider: Dict[str, Any]
    ssh: SSHConfig = field(default_factory=SSHConfig)
    timeout: float = 30.0
    bridge_factory: Callable[..., RemoteBridge] = RemoteBridge
    _bridge: Optional[RemoteBridge] = field(default=None, init=False, repr=False)

    @classmethod
    def from_provider(
        cls,
        provider: Dict[str, Any],
        *,
        timeout: float = 30.0,
        bridge_factory: Callable[..., RemoteBridge] = RemoteBridge,
    ) -> "UnraidAdapter":
        ssh = _extract_ssh_config(provider)
        return cls(
            provider=provider,
            ssh=ssh,
            timeout=timeout,
            bridge_factory=bridge_factory,
        )

    # ------------------------------------------------------------------ helpers
    @property
    def base_url(self) -> str:
        return str(
            self.provider.get("base_url")
            or self.provider.get("base")
            or self.provider.get("endpoint")
            or ""
        ).strip()

    def _ensure_bridge(self) -> RemoteBridge:
        if self._bridge is None:
            if not self.ssh.host:
                raise RuntimeError("SSH host missing for Unraid provider")
            self._bridge = self.bridge_factory(
                self.ssh.host,
                user=self.ssh.user,
                port=self.ssh.port,
                identity_file=self.ssh.identity_file,
                ssh_command=self.ssh.ssh_command,
                scp_command=self.ssh.scp_command,
                connect_timeout=10.0,
            )
        return self._bridge

    async def _run_command(
        self, command: str, *, timeout: Optional[float] = None
    ) -> subprocess.CompletedProcess[str]:
        bridge = self._ensure_bridge()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: bridge.run(
                command,
                check=False,
                timeout=timeout or self.timeout,
            ),
        )

    async def _capability_probe(self) -> RemoteCapabilityReport:
        bridge = self._ensure_bridge()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, bridge.capability_probe)

    # ------------------------------------------------------------------ public API
    async def health(self) -> Dict[str, Any]:
        if not self.ssh.host:
            return {"ok": False, "error": "SSH host not configured"}
        try:
            report = await self._capability_probe()
        except Exception as exc:  # pragma: no cover - remote dependent
            LOGGER.warning("Unraid capability probe failed: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {
            "ok": report.ok,
            "summary": report.summary,
            "details": report.details,
        }

    async def fetch_quota(self) -> Dict[str, Any]:
        if not self.ssh.host:
            return {"ok": False, "error": "SSH host not configured"}

        commands = {
            "gpu": "nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader",
            "disk": "df -h --output=source,size,used,avail,pcent,target /mnt/cache /mnt/user",
            "docker": "docker ps --format '{{json .}}'",
        }

        results: Dict[str, Dict[str, Any]] = {}
        overall_ok = True
        for key, command in commands.items():
            try:
                proc = await self._run_command(command, timeout=45.0)
            except Exception as exc:  # pragma: no cover - remote dependent
                results[key] = {"ok": False, "error": str(exc)}
                overall_ok = False
                continue
            entry = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            }
            if proc.returncode != 0:
                overall_ok = False
            results[key] = entry

        return {"ok": overall_ok, "results": results}

    async def fetch_templates(self) -> Dict[str, Any]:
        """Return docker images and compose stacks that can act as templates."""
        if not self.ssh.host:
            return {"ok": False, "error": "SSH host not configured"}
        try:
            images_proc = await self._run_command(
                "docker images --format '{{json .}}'", timeout=45.0
            )
        except Exception as exc:  # pragma: no cover - remote dependent
            return {"ok": False, "error": str(exc)}

        templates: List[Dict[str, Any]] = []
        for line in images_proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            repository = data.get("Repository")
            tag = data.get("Tag")
            if repository:
                templates.append(
                    {
                        "id": f"{repository}:{tag}" if tag else repository,
                        "repository": repository,
                        "tag": tag,
                        "size": data.get("Size"),
                        "created_since": data.get("CreatedSince"),
                        "raw": data,
                    }
                )

        return {
            "ok": images_proc.returncode == 0,
            "templates": templates,
            "docker_returncode": images_proc.returncode,
        }

    async def comfyui_health(self) -> Dict[str, Any]:
        base = self.base_url
        if not base:
            return {"ok": False, "error": "base_url missing"}
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: generic_providers.comfyui_health(base)
        )

    async def bootstrap(
        self,
        *,
        output_dir: Path,
        workspace: Optional[Path] = None,
        log_hook: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Perform a lightweight bootstrap: prepare folders, capture diagnostics, sync manifests."""
        if not self.ssh.host:
            return {"ok": False, "error": "SSH host not configured"}

        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        logs: List[str] = []
        artifacts: List[Path] = []
        executed_commands: List[Dict[str, Any]] = []
        overall_ok = True

        def _emit(message: str) -> None:
            logs.append(message)
            LOGGER.info("[Unraid bootstrap] %s", message)
            if log_hook:
                try:
                    log_hook(message)
                except Exception:  # pragma: no cover - defensive
                    LOGGER.debug("Unraid bootstrap log hook failed", exc_info=True)

        _emit("Starting Unraid bootstrap workflow")

        setup_commands = [
            "mkdir -p ~/comfyvn/bootstrap ~/comfyvn/models ~/comfyvn/custom_nodes",
            "mkdir -p ~/comfyvn/ComfyUI/custom_nodes ~/comfyvn/ComfyUI/models",
            "python3 - <<'PY'\nimport json, os\nroot=os.path.expanduser('~/comfyvn')\ninfo={'root': root, 'dirs': sorted(os.listdir(root))}\nprint(json.dumps(info))\nPY",
        ]

        for idx, command in enumerate(setup_commands, start=1):
            try:
                proc = await self._run_command(command, timeout=90.0)
            except Exception as exc:  # pragma: no cover - remote dependent
                overall_ok = False
                result = {
                    "command": command,
                    "ok": False,
                    "error": str(exc),
                }
                executed_commands.append(result)
                _emit(f"Step {idx} failed: {exc}")
                continue
            result = {
                "command": command,
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "ok": proc.returncode == 0,
            }
            executed_commands.append(result)
            if proc.returncode == 0:
                _emit(f"Step {idx} completed successfully")
            else:
                overall_ok = False
                _emit(f"Step {idx} returned {proc.returncode}")

        # Collect quota and templates for diagnostics.
        quota_info = await self.fetch_quota()
        templates_info = await self.fetch_templates()
        comfy_health = await self.comfyui_health()

        report_payload = {
            "commands": executed_commands,
            "quota": quota_info,
            "templates": templates_info,
            "comfyui": comfy_health,
        }
        report_path = output_dir / "unraid_bootstrap_report.json"
        report_path.write_text(
            json.dumps(report_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        artifacts.append(report_path)
        _emit(f"Bootstrap report captured -> {report_path}")

        # Snapshot workspace manifest for future rsync.
        workspace_manifest: Optional[Path] = None
        if workspace and workspace.exists():
            files: List[str] = []
            for path in workspace.rglob("*"):
                if path.is_file():
                    try:
                        rel = path.relative_to(workspace)
                    except ValueError:
                        rel = path.name
                    files.append(str(rel))
            manifest = {
                "root": str(workspace),
                "files": files,
                "total_files": len(files),
            }
            workspace_manifest = output_dir / "workspace_manifest.json"
            workspace_manifest.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            artifacts.append(workspace_manifest)
            _emit(
                f"Workspace manifest created with {len(files)} file(s) -> {workspace_manifest}"
            )
        else:
            _emit("Workspace not provided; skipping manifest generation")

        # Generate local artifact to mimic remote pullback.
        log_path = output_dir / "bootstrap.log"
        log_path.write_text("\n".join(logs), encoding="utf-8")
        artifacts.append(log_path)

        _emit("Unraid bootstrap complete")

        return {
            "ok": overall_ok and quota_info.get("ok", False),
            "logs": logs,
            "artifacts": _artifact_summary(artifacts),
            "details": report_payload,
        }


__all__ = ["SSHConfig", "UnraidAdapter"]
