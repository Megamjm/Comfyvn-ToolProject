from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderTemplate:
    """Describes a provider template presented to the user as a quick-start preset."""

    id: str
    name: str
    kind: str
    service: str
    base_url: str
    gpu: str
    fields: Iterable[str]
    priority: int


DEFAULT_PROVIDER_TEMPLATES: List[ProviderTemplate] = [
    ProviderTemplate(
        id="local",
        name="Local ComfyUI",
        kind="local",
        service="comfyui",
        base_url="http://127.0.0.1:8188",
        gpu="auto",
        fields=[],
        priority=0,
    ),
    ProviderTemplate(
        id="runpod",
        name="RunPod",
        kind="remote",
        service="runpod",
        base_url="https://api.runpod.io/v2/",
        gpu="A10G",
        fields=["api_key"],
        priority=10,
    ),
    ProviderTemplate(
        id="vast",
        name="Vast.ai",
        kind="remote",
        service="vast.ai",
        base_url="https://api.vast.ai/v0/",
        gpu="RTX4090",
        fields=["api_key"],
        priority=20,
    ),
    ProviderTemplate(
        id="lambda",
        name="Lambda Labs",
        kind="remote",
        service="lambda",
        base_url="https://cloud.lambdalabs.com/api/v1/",
        gpu="A100",
        fields=["api_key"],
        priority=30,
    ),
    ProviderTemplate(
        id="paperspace",
        name="Paperspace Gradient",
        kind="remote",
        service="paperspace",
        base_url="https://api.paperspace.io",
        gpu="RTX3090",
        fields=["api_key"],
        priority=40,
    ),
    ProviderTemplate(
        id="coreweave",
        name="CoreWeave",
        kind="remote",
        service="coreweave",
        base_url="https://api.coreweave.com",
        gpu="A40",
        fields=["username", "password"],
        priority=50,
    ),
    ProviderTemplate(
        id="google",
        name="Google Cloud",
        kind="remote",
        service="gcp",
        base_url="https://compute.googleapis.com",
        gpu="L4",
        fields=["service_account_json"],
        priority=60,
    ),
    ProviderTemplate(
        id="azure",
        name="Microsoft Azure",
        kind="remote",
        service="azure",
        base_url="https://management.azure.com",
        gpu="A10",
        fields=["tenant_id", "client_id", "client_secret"],
        priority=70,
    ),
    ProviderTemplate(
        id="aws",
        name="AWS EC2",
        kind="remote",
        service="aws",
        base_url="https://ec2.amazonaws.com",
        gpu="A10G",
        fields=["access_key", "secret_key"],
        priority=80,
    ),
    ProviderTemplate(
        id="unraid",
        name="Unraid / LAN Node",
        kind="remote",
        service="lan",
        base_url="http://unraid.local:8001",
        gpu="Local GPU",
        fields=["endpoint"],
        priority=90,
    ),
]


def _slugify(value: str) -> str:
    keep = []
    for ch in value.lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in {"-", "_"}:
            keep.append(ch)
        elif ch.isspace():
            keep.append("-")
    slug = "".join(keep).strip("-")
    return slug or "provider"


class ComputeProviderRegistry:
    """Persisted registry of compute providers (local + remote)."""

    def __init__(
        self,
        path: str | Path = "data/settings/providers.json",
        templates: Optional[Iterable[ProviderTemplate]] = None,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.templates = list(templates or DEFAULT_PROVIDER_TEMPLATES)
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {"providers": []}
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    self._data = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.warning("Provider registry corrupt; rebuilding (%s)", exc)
                    self._data = {"providers": []}
            else:
                self._data = {"providers": []}
            self._data.setdefault("providers", [])
            self._ensure_local_locked()
            self._save_locked()

    def _save_locked(self) -> None:
        self.path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _ensure_local_locked(self) -> None:
        providers = self._data.get("providers", [])
        if not any(p.get("id") == "local" for p in providers):
            template = next((t for t in self.templates if t.id == "local"), None)
            providers.append(
                {
                    "id": "local",
                    "name": template.name if template else "Local GPU",
                    "kind": "local",
                    "service": "comfyui",
                    "base_url": template.base_url if template else "http://127.0.0.1:8188",
                    "active": True,
                    "priority": 0,
                    "meta": {"gpu": "auto"},
                    "config": {},
                    "last_health": {"ok": True, "ts": None},
                    "created_at": None,
                    "updated_at": None,
                }
            )
            self._data["providers"] = providers

    def _find_index_locked(self, provider_id: str) -> Optional[int]:
        providers = self._data.get("providers", [])
        for idx, entry in enumerate(providers):
            if entry.get("id") == provider_id:
                return idx
        return None

    def _mask(self, value: Any, key: str) -> Any:
        if not isinstance(value, str):
            return value
        lowered = key.lower()
        if any(token in lowered for token in ("key", "secret", "token", "password")):
            return "*" * len(value) if value else value
        return value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def templates_public(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": t.id,
                "name": t.name,
                "kind": t.kind,
                "service": t.service,
                "base_url": t.base_url,
                "gpu": t.gpu,
                "fields": list(t.fields),
                "priority": t.priority,
            }
            for t in self.templates
        ]

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            providers = sorted(
                self._data.get("providers", []),
                key=lambda row: row.get("priority", 999),
            )
            masked = []
            for entry in providers:
                copy = json.loads(json.dumps(entry))
                config = copy.get("config") or {}
                copy["config"] = {
                    key: self._mask(val, key) for key, val in config.items()
                }
                masked.append(copy)
            return masked

    def get(self, provider_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            idx = self._find_index_locked(provider_id)
            if idx is None:
                return None
            entry = self._data["providers"][idx]
            return json.loads(json.dumps(entry))

    def register(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict")
        provider_id = payload.get("id") or _slugify(payload.get("name", "provider"))
        name = payload.get("name") or provider_id
        kind = payload.get("kind", "remote")
        service = payload.get("service") or kind
        base_url = payload.get("base_url") or payload.get("endpoint") or ""
        if not base_url:
            raise ValueError("base_url is required")
        config = payload.get("config") or {}
        meta = payload.get("meta") or {}
        active = bool(payload.get("active", True))

        with self._lock:
            idx = self._find_index_locked(provider_id)
            now = payload.get("ts") or payload.get("updated_at")
            if idx is None:
                priority = payload.get("priority")
                if priority is None:
                    priorities = [
                        row.get("priority", 0) for row in self._data.get("providers", [])
                    ]
                    priority = (max(priorities) + 10) if priorities else 10
                entry = {
                    "id": provider_id,
                    "name": name,
                    "kind": kind,
                    "service": service,
                    "base_url": base_url,
                    "active": active,
                    "priority": priority,
                    "meta": meta,
                    "config": config,
                    "last_health": {"ok": None, "ts": None},
                    "created_at": now,
                    "updated_at": now,
                }
                self._data.setdefault("providers", []).append(entry)
            else:
                entry = self._data["providers"][idx]
                entry.update(
                    {
                        "name": name,
                        "kind": kind,
                        "service": service,
                        "base_url": base_url,
                        "active": active,
                        "meta": meta,
                    }
                )
                entry["config"] = config
                if "priority" in payload:
                    entry["priority"] = int(payload["priority"])
                entry["updated_at"] = now

            self._save_locked()
            LOGGER.debug("Provider registry updated: %s", provider_id)
            return json.loads(json.dumps(entry))

    def remove(self, provider_id: str) -> bool:
        if provider_id == "local":
            raise ValueError("Cannot remove the built-in local provider")
        with self._lock:
            idx = self._find_index_locked(provider_id)
            if idx is None:
                return False
            self._data["providers"].pop(idx)
            self._save_locked()
            LOGGER.info("Removed provider '%s' from registry", provider_id)
            return True

    def set_active(self, provider_id: str, active: bool) -> Optional[Dict[str, Any]]:
        with self._lock:
            idx = self._find_index_locked(provider_id)
            if idx is None:
                return None
            entry = self._data["providers"][idx]
            entry["active"] = bool(active)
            self._save_locked()
            return json.loads(json.dumps(entry))

    def set_priority_order(self, order: List[str]) -> List[Dict[str, Any]]:
        with self._lock:
            providers = self._data.get("providers", [])
            order_map = {pid: idx for idx, pid in enumerate(order)}
            for entry in providers:
                pid = entry.get("id")
                if pid in order_map:
                    entry["priority"] = order_map[pid]
            self._save_locked()
            return self.list()

    def record_health(self, provider_id: str, status: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            idx = self._find_index_locked(provider_id)
            if idx is None:
                return None
            entry = self._data["providers"][idx]
            entry.setdefault("last_health", {})
            entry["last_health"].update(status or {})
            entry["last_health"]["ts"] = status.get("ts") or int(time.time() * 1000)
            self._save_locked()
            return json.loads(json.dumps(entry))

    def active_providers(self) -> List[Dict[str, Any]]:
        return [row for row in self.list() if row.get("active")]

    def remote_endpoints(self) -> List[str]:
        return [
            row["base_url"]
            for row in self.active_providers()
            if row.get("kind") == "remote"
        ]


_REGISTRY: ComputeProviderRegistry | None = None


def get_provider_registry() -> ComputeProviderRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ComputeProviderRegistry()
    return _REGISTRY
