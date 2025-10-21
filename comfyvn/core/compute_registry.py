from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from comfyvn.config.runtime_paths import settings_file
from comfyvn.core.provider_profiles import CURATED_PROVIDER_PROFILES, ProviderProfile

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
    metadata: Dict[str, Any] = field(default_factory=dict)
    policy_hints: Dict[str, str] = field(default_factory=dict)
    preferred_workloads: Iterable[str] = field(default_factory=tuple)


def _template_from_profile(profile: ProviderProfile) -> ProviderTemplate:
    metadata = dict(profile.metadata)
    metadata.setdefault("gpu", profile.default_gpu)
    metadata.setdefault("auth_fields", list(profile.auth_fields))
    metadata.setdefault("policy_hints", dict(profile.policy_hints))
    metadata.setdefault("preferred_workloads", list(profile.preferred_workloads))
    return ProviderTemplate(
        id=profile.id,
        name=profile.name,
        kind=profile.kind,
        service=profile.service,
        base_url=profile.base_url,
        gpu=profile.default_gpu,
        fields=list(profile.auth_fields),
        priority=profile.priority,
        metadata=metadata,
        policy_hints=dict(profile.policy_hints),
        preferred_workloads=list(profile.preferred_workloads),
    )


DEFAULT_PROVIDER_TEMPLATES: List[ProviderTemplate] = [
    _template_from_profile(profile) for profile in CURATED_PROVIDER_PROFILES
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
        path: str | Path = settings_file("providers.json"),
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
    def _template_for(
        self,
        *,
        provider_id: Optional[str] = None,
        service: Optional[str] = None,
    ) -> Optional[ProviderTemplate]:
        provider_id = (provider_id or "").lower() or None
        service = (service or "").lower() or None
        for template in self.templates:
            if provider_id and template.id == provider_id:
                return template
            if service and template.service == service:
                return template
        return None

    def _template_meta(self, template: Optional[ProviderTemplate]) -> Dict[str, Any]:
        if not template:
            return {}
        meta = json.loads(json.dumps(template.metadata))
        meta.setdefault("gpu", template.gpu)
        if template.policy_hints:
            meta.setdefault("policy_hints", dict(template.policy_hints))
        if template.preferred_workloads:
            meta.setdefault("preferred_workloads", list(template.preferred_workloads))
        meta.setdefault("auth_fields", list(template.fields))
        return meta

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
            template = self._template_for(provider_id="local")
            meta = self._template_meta(template)
            if not meta:
                meta = {"gpu": "auto"}
            providers.append(
                {
                    "id": "local",
                    "name": template.name if template else "Local GPU",
                    "kind": template.kind if template else "local",
                    "service": template.service if template else "comfyui",
                    "base_url": template.base_url if template else "http://127.0.0.1:8188",
                    "active": True,
                    "priority": 0,
                    "meta": meta,
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
        if self._is_secret_key(key):
            return "*" * len(value) if value else value
        return value

    def _is_secret_key(self, key: str) -> bool:
        lowered = (key or "").lower()
        return any(token in lowered for token in ("key", "secret", "token", "password"))

    def _generate_unique_id(self, base: str) -> str:
        with self._lock:
            slug = _slugify(base or "provider")
            existing = {row.get("id") for row in self._data.get("providers", [])}
            if slug not in existing:
                return slug
            suffix = 2
            while True:
                candidate = f"{slug}-{suffix}"
                if candidate not in existing:
                    return candidate
                suffix += 1

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
                "metadata": json.loads(json.dumps(t.metadata)),
                "policy_hints": dict(t.policy_hints),
                "preferred_workloads": list(t.preferred_workloads),
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
        template = self._template_for(provider_id=provider_id, service=service)
        template_meta = self._template_meta(template)
        if template_meta:
            merged_meta = dict(template_meta)
            merged_meta.update(meta)
            meta = merged_meta

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

    def create_from_template(
        self,
        template_id: str,
        *,
        provider_id: Optional[str] = None,
        name: Optional[str] = None,
        base_url: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        meta_overrides: Optional[Dict[str, Any]] = None,
        priority: Optional[int] = None,
        active: bool = True,
    ) -> Dict[str, Any]:
        template = self._template_for(provider_id=template_id, service=template_id)
        if template is None:
            raise ValueError(f"template '{template_id}' not found")

        with self._lock:
            if provider_id:
                candidate = _slugify(provider_id)
                if self._find_index_locked(candidate) is not None:
                    raise ValueError(f"provider '{candidate}' already exists")
                final_id = candidate
            else:
                base_name = name or template.name or template.id
                final_id = self._generate_unique_id(base_name)

        payload = {
            "id": final_id,
            "name": name or template.name,
            "kind": template.kind,
            "service": template.service,
            "base_url": base_url or template.base_url,
            "config": config or {},
            "meta": meta_overrides or {},
            "priority": priority if priority is not None else template.priority,
            "active": active,
        }
        return self.register(payload)

    def export_all(self, *, mask_secrets: bool = True) -> Dict[str, Any]:
        with self._lock:
            providers = json.loads(json.dumps(self._data.get("providers", [])))
            if mask_secrets:
                for entry in providers:
                    config = entry.get("config") or {}
                    entry["config"] = {
                        key: value
                        for key, value in config.items()
                        if not self._is_secret_key(key)
                    }
            return {
                "version": 1,
                "exported_at": int(time.time() * 1000),
                "providers": providers,
            }

    def import_data(
        self,
        data: Dict[str, Any] | Sequence[Dict[str, Any]],
        *,
        replace: bool = False,
        overwrite: bool = True,
    ) -> List[Dict[str, Any]]:
        providers: Optional[List[Dict[str, Any]]] = None
        if isinstance(data, dict):
            raw = data.get("providers")
            if raw is not None and not isinstance(raw, list):
                raise TypeError("payload.providers must be a list")
            providers = raw
        elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
            providers = list(data)  # type: ignore[arg-type]
        if providers is None:
            raise TypeError("import payload must contain a list of providers")

        imported: List[Dict[str, Any]] = []
        last_health_updates: List[tuple[str, Dict[str, Any]]] = []

        with self._lock:
            if replace:
                self._data["providers"] = []

            for entry in providers:
                if not isinstance(entry, dict):
                    continue
                provider_id = entry.get("id")
                base_url = entry.get("base_url")
                if not provider_id or not base_url:
                    LOGGER.debug("Skipping provider import missing id/base_url: %s", entry)
                    continue
                if (
                    not overwrite
                    and self._find_index_locked(provider_id) is not None
                ):
                    LOGGER.debug("Skipping provider '%s' (exists and overwrite disabled)", provider_id)
                    continue

                payload = {
                    "id": provider_id,
                    "name": entry.get("name"),
                    "kind": entry.get("kind"),
                    "service": entry.get("service"),
                    "base_url": base_url,
                    "config": entry.get("config") or {},
                    "meta": entry.get("meta") or {},
                    "priority": entry.get("priority"),
                    "active": entry.get("active", True),
                    "ts": entry.get("updated_at") or entry.get("ts"),
                }

                registered = self.register(payload)
                imported.append(registered)
                last_health = entry.get("last_health")
                if isinstance(last_health, dict):
                    last_health_updates.append((registered["id"], last_health))

            for provider_id, status in last_health_updates:
                idx = self._find_index_locked(provider_id)
                if idx is None:
                    continue
                row = self._data["providers"][idx]
                row["last_health"] = status

            self._ensure_local_locked()
            self._save_locked()
            return imported

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
