from __future__ import annotations

import json
import logging
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RemoteCapabilityReport:
    """Result of probing a remote compute provider."""

    ok: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)


class RemoteBridge:
    """Minimal SSH-based bridge for remote compute providers."""

    def __init__(
        self,
        host: str,
        *,
        user: Optional[str] = None,
        port: Optional[int] = None,
        identity_file: Optional[Path] = None,
        ssh_command: str = "ssh",
        scp_command: str = "scp",
        connect_timeout: float = 10.0,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.host = host
        self.user = user
        self.port = port
        self.identity_file = identity_file
        self.ssh_command = ssh_command
        self.scp_command = scp_command
        self.connect_timeout = connect_timeout
        self.env = env

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------
    def _remote_target(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    def _build_ssh_args(self, extra: Optional[Sequence[str]] = None) -> list[str]:
        args: list[str] = [self.ssh_command]
        if self.port:
            args.extend(["-p", str(self.port)])
        if self.identity_file:
            args.extend(["-i", str(self.identity_file)])
        args.extend(["-o", f"ConnectTimeout={int(self.connect_timeout)}"])
        args.append(self._remote_target())
        if extra:
            args.extend(extra)
        return args

    def run(
        self,
        command: str | Sequence[str],
        *,
        check: bool = True,
        timeout: float = 120.0,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a command remotely via SSH."""
        if isinstance(command, str):
            remote_cmd = command
        else:
            remote_cmd = " ".join(shlex.quote(part) for part in command)
        args = self._build_ssh_args([remote_cmd])
        LOGGER.debug(
            "RemoteBridge executing: %s", " ".join(shlex.quote(a) for a in args)
        )
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
            timeout=timeout,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode,
                args,
                output=proc.stdout,
                stderr=proc.stderr,
            )
        return proc

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------
    def push(
        self,
        source: Path,
        destination: str | Path,
        *,
        recursive: bool = False,
        timeout: float = 300.0,
    ) -> None:
        """Upload a file or directory to the remote host."""
        dest = f"{self._remote_target()}:{destination}"
        args = [self.scp_command]
        if recursive:
            args.append("-r")
        if self.port:
            args.extend(["-P", str(self.port)])
        if self.identity_file:
            args.extend(["-i", str(self.identity_file)])
        args.extend([str(source), dest])
        LOGGER.debug("RemoteBridge push: %s", " ".join(shlex.quote(a) for a in args))
        subprocess.run(args, check=True, timeout=timeout, env=self.env)

    def pull(
        self,
        source: str | Path,
        destination: Path,
        *,
        recursive: bool = False,
        timeout: float = 300.0,
    ) -> None:
        """Download a file or directory from the remote host."""
        src = f"{self._remote_target()}:{source}"
        args = [self.scp_command]
        if recursive:
            args.append("-r")
        if self.port:
            args.extend(["-P", str(self.port)])
        if self.identity_file:
            args.extend(["-i", str(self.identity_file)])
        args.extend([src, str(destination)])
        LOGGER.debug("RemoteBridge pull: %s", " ".join(shlex.quote(a) for a in args))
        subprocess.run(args, check=True, timeout=timeout, env=self.env)

    # ------------------------------------------------------------------
    # Capability probe
    # ------------------------------------------------------------------
    def capability_probe(self) -> RemoteCapabilityReport:
        """Gather GPU/driver/tooling information from the remote host."""
        diagnostics: Dict[str, Any] = {}
        ok = True

        for command, parser in (
            (
                "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader",
                self._parse_gpu,
            ),
            ("ffmpeg -version", self._parse_ffmpeg),
            (
                "python3 -c \"import torch, json; print(json.dumps({'cuda': torch.cuda.is_available(), 'version': torch.__version__}))\"",
                self._parse_torch,
            ),
        ):
            try:
                proc = self.run(command, check=False, timeout=20.0)
                diagnostics.update(parser(proc))
                if proc.returncode != 0:
                    ok = False
            except (
                Exception
            ) as exc:  # pragma: no cover - remote connectivity issues are environment-specific
                LOGGER.warning("Remote capability check failed (%s): %s", command, exc)
                ok = False

        summary = "remote ready" if ok else "remote requires attention"
        return RemoteCapabilityReport(ok=ok, summary=summary, details=diagnostics)

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------
    def _parse_gpu(self, proc: subprocess.CompletedProcess[str]) -> Dict[str, Any]:
        info: Dict[str, Any] = {"nvidia_smi": {"returncode": proc.returncode}}
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        gpus: list[Dict[str, str]] = []
        for line in lines:
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 3:
                gpus.append(
                    {
                        "name": parts[0],
                        "memory_total": parts[1],
                        "driver_version": parts[2],
                    }
                )
        info["nvidia_smi"]["gpus"] = gpus
        if proc.stderr:
            info["nvidia_smi"]["stderr"] = proc.stderr.strip()
        return info

    def _parse_ffmpeg(self, proc: subprocess.CompletedProcess[str]) -> Dict[str, Any]:
        first_line = (proc.stdout.splitlines() or [""])[0]
        return {
            "ffmpeg": {
                "returncode": proc.returncode,
                "version": first_line.strip(),
                "stderr": proc.stderr.strip() if proc.stderr else "",
            }
        }

    def _parse_torch(self, proc: subprocess.CompletedProcess[str]) -> Dict[str, Any]:
        details: Dict[str, Any] = {
            "torch": {
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip() if proc.stderr else "",
            }
        }
        try:
            if proc.stdout:
                details["torch"]["json"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            LOGGER.debug("torch probe stdout not JSON: %s", proc.stdout)
        return details


__all__ = ["RemoteBridge", "RemoteCapabilityReport"]
