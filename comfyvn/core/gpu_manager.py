from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from comfyvn.config.runtime_paths import settings_file

try:  # torch is optional at runtime
    import torch  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    torch = None

from comfyvn.core.compute_registry import ComputeProviderRegistry, get_provider_registry

LOGGER = logging.getLogger(__name__)

POLICY_MODES = {"auto", "manual", "sticky"}


class GPUManager:
    """Tracks available compute devices and enforces GPU policy selection."""

    def __init__(
        self,
        config_path: str | Path = settings_file("gpu_policy.json"),
        provider_registry: Optional[ComputeProviderRegistry] = None,
    ):
        self.path = Path(config_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.registry = provider_registry or get_provider_registry()
        self._state = self._load_state()
        self._devices: List[Dict[str, Any]] = []
        self.refresh()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load_state(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                data.setdefault("mode", "auto")
                data.setdefault("manual_device", "cpu")
                data.setdefault("sticky_device", None)
                data.setdefault("last_selected", None)
                return data
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("GPU policy file corrupt (%s); resetting", exc)
        return {
            "mode": "auto",
            "manual_device": "cpu",
            "sticky_device": None,
            "last_selected": None,
        }

    def _save_state(self) -> None:
        self.path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------
    def refresh(self) -> List[Dict[str, Any]]:
        devices: List[Dict[str, Any]] = [self._cpu_entry()]
        devices.extend(self._discover_local_gpus())
        devices.extend(self._discover_remote_devices())
        self._devices = devices
        return devices

    def _cpu_entry(self) -> Dict[str, Any]:
        return {
            "id": "cpu",
            "name": "CPU",
            "kind": "cpu",
            "available": True,
            "memory_total": None,
            "memory_used": None,
            "source": "local",
        }

    def _discover_local_gpus(self) -> List[Dict[str, Any]]:
        gpus: List[Dict[str, Any]] = []
        # Prefer torch when available to include VRAM metadata
        try:
            if torch and torch.cuda.is_available():
                count = torch.cuda.device_count()
                for idx in range(count):
                    props = torch.cuda.get_device_properties(idx)
                    mem_total = round(props.total_memory / (1024**2), 2)
                    mem_used = (
                        round(torch.cuda.memory_allocated(idx) / (1024**2), 2)
                        if hasattr(torch.cuda, "memory_allocated")
                        else None
                    )
                    gpus.append(
                        {
                            "id": f"cuda:{idx}",
                            "name": props.name,
                            "kind": "gpu",
                            "available": True,
                            "memory_total": mem_total,
                            "memory_used": mem_used,
                            "source": "torch",
                        }
                    )
                return gpus
        except Exception as exc:
            LOGGER.debug("Torch GPU discovery failed: %s", exc)

        # Fallback to nvidia-smi parsing
        if shutil.which("nvidia-smi"):
            try:
                out = subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    stderr=subprocess.DEVNULL,
                ).decode()
                for line in out.strip().splitlines():
                    idx, name, mem_total, mem_used, util, temp = [
                        part.strip() for part in line.split(",")
                    ]
                    gpus.append(
                        {
                            "id": f"cuda:{idx}",
                            "name": name,
                            "kind": "gpu",
                            "available": True,
                            "memory_total": float(mem_total),
                            "memory_used": float(mem_used),
                            "utilization": int(util),
                            "temperature": int(temp),
                            "source": "nvidia-smi",
                        }
                    )
            except Exception as exc:  # pragma: no cover - external binary
                LOGGER.debug("nvidia-smi discovery failed: %s", exc)
        return gpus

    def _discover_remote_devices(self) -> List[Dict[str, Any]]:
        remotes: List[Dict[str, Any]] = []
        if not self.registry:
            return remotes
        for entry in self.registry.list():
            if entry.get("kind") != "remote":
                continue
            last_health = entry.get("last_health") or {}
            remotes.append(
                {
                    "id": f"remote:{entry['id']}",
                    "name": entry.get("name", entry["id"]),
                    "kind": "remote",
                    "available": bool(last_health.get("ok", False)),
                    "source": entry.get("service"),
                    "meta": {
                        "priority": entry.get("priority"),
                        "base_url": entry.get("base_url"),
                    },
                    "last_health": last_health,
                }
            )
        return remotes

    # ------------------------------------------------------------------
    # Policy interaction
    # ------------------------------------------------------------------
    def list_all(self, *, refresh: bool = False) -> List[Dict[str, Any]]:
        if refresh or not self._devices:
            self.refresh()
        return list(self._devices)

    def list_local(self, *, refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Return only locally available devices (CPU + on-box GPUs).

        Remote providers are filtered out so UI callers can present a quick
        snapshot of hardware that is immediately accessible without network hops.
        """
        devices = self.list_all(refresh=refresh)
        return [device for device in devices if device.get("kind") != "remote"]

    def get_policy(self) -> Dict[str, Any]:
        return dict(self._state)

    def set_policy(self, mode: str, device: Optional[str] = None) -> Dict[str, Any]:
        mode = (mode or "").lower().strip()
        if mode not in POLICY_MODES:
            raise AssertionError(
                f"mode must be one of: {', '.join(sorted(POLICY_MODES))}"
            )
        self._state["mode"] = mode
        if device:
            self._state["manual_device"] = device
        self._save_state()
        LOGGER.info(
            "GPU policy set -> mode=%s, device=%s",
            mode,
            device or self._state.get("manual_device"),
        )
        return self.get_policy()

    def set_manual_device(self, device: str) -> Dict[str, Any]:
        if not device:
            raise ValueError("device must be provided")
        self._state["manual_device"] = device
        self._save_state()
        LOGGER.debug("Manual GPU device set -> %s", device)
        return self.get_policy()

    def record_selection(self, device: str) -> None:
        self._state["last_selected"] = device
        if self._state.get("mode") == "sticky":
            self._state["sticky_device"] = device
        self._save_state()

    # ------------------------------------------------------------------
    # Device selection
    # ------------------------------------------------------------------
    def select_device(
        self,
        *,
        prefer: Optional[str] = None,
        requirements: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        devices = {device["id"]: device for device in self.list_all(refresh=True)}
        requirements = requirements or {}
        mode = self._state.get("mode", "auto")

        def available(device_id: Optional[str]) -> bool:
            if not device_id:
                return False
            device = devices.get(device_id)
            return bool(device and device.get("available", True))

        def finalize_choice(chosen_id: str, reason: str) -> Dict[str, Any]:
            self.record_selection(chosen_id)
            device_info = devices.get(chosen_id, {})
            kind = device_info.get("kind")
            if not kind:
                if chosen_id.startswith("remote:"):
                    kind = "remote"
                elif chosen_id.startswith("cuda:"):
                    kind = "gpu"
                else:
                    kind = "cpu"
            selection: Dict[str, Any] = {
                "id": chosen_id,
                "device": chosen_id,
                "policy": mode,
                "reason": reason,
                "kind": kind,
                "name": device_info.get("name"),
                "available": device_info.get("available", True),
                "source": device_info.get("source"),
            }
            if (
                "memory_total" in device_info
                and device_info.get("memory_total") is not None
            ):
                selection["memory_total"] = device_info.get("memory_total")
            if (
                "memory_used" in device_info
                and device_info.get("memory_used") is not None
            ):
                selection["memory_used"] = device_info.get("memory_used")
            if (
                "utilization" in device_info
                and device_info.get("utilization") is not None
            ):
                selection["utilization"] = device_info.get("utilization")
            if device_info.get("kind") == "remote" or chosen_id.startswith("remote:"):
                segments = chosen_id.split(":", 1)
                if len(segments) == 2:
                    selection["provider_id"] = segments[1]
                selection["meta"] = device_info.get("meta")
                selection["last_health"] = device_info.get("last_health")
            return selection

        # 1. Honour explicit preference
        if prefer and available(prefer):
            return finalize_choice(prefer, "preferred")

        # 2. Policy-based selection
        if mode == "manual":
            manual_device = self._state.get("manual_device")
            chosen = manual_device if available(manual_device) else "cpu"
            return finalize_choice(chosen, "manual")

        if mode == "sticky":
            sticky = self._state.get("sticky_device")
            if available(sticky):
                return finalize_choice(sticky, "sticky")

        # 3. Auto selection — prefer local GPUs, then remote, then CPU
        min_memory = float(requirements.get("memory_min_mb") or 0)
        candidates = []
        for device_id, device in devices.items():
            if not device.get("available", True):
                continue
            if device["kind"] == "gpu":
                mem_total = float(device.get("memory_total") or 0)
                if mem_total and mem_total < min_memory:
                    continue
                candidates.append((0, -mem_total, device_id))
            elif device["kind"] == "remote":
                priority = device.get("meta", {}).get("priority", 999)
                candidates.append((1, priority, device_id))
            else:  # CPU fallback
                candidates.append((2, 0, device_id))

        if not candidates:
            chosen = "cpu"
        else:
            candidates.sort()
            chosen = candidates[0][2]
        return finalize_choice(chosen, "auto")

    def annotate_payload(self, payload: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        selection = self.select_device(**kwargs)
        payload = dict(payload or {})
        payload["device"] = selection["device"]
        payload.setdefault("meta", {})["compute_policy"] = selection
        return payload


_GPU_MANAGER: GPUManager | None = None


def get_gpu_manager() -> GPUManager:
    global _GPU_MANAGER
    if _GPU_MANAGER is None:
        _GPU_MANAGER = GPUManager()
    return _GPU_MANAGER
