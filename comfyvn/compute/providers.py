from __future__ import annotations

"""Simple provider registry for local/remote compute backends."""

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, Optional

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Provider:
    """Represents a compute provider entry."""

    id: str
    kind: str  # runpod | unraid | custom
    base: str
    meta: Dict[str, Any]


def _coerce_meta(meta: Any) -> Dict[str, Any]:
    if isinstance(meta, MutableMapping):
        return {str(k): v for k, v in meta.items()}
    return {}


class ProviderRegistry:
    """Thread-safe provider registry with optional JSON persistence."""

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        seed: Optional[Iterable[Provider | Dict[str, Any]]] = None,
    ) -> None:
        self._items: Dict[str, Provider] = {}
        self._lock = threading.RLock()
        self._storage_path = Path(storage_path).expanduser() if storage_path else None
        if self._storage_path:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()
        if seed:
            for entry in seed:
                try:
                    self.add(entry)
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.debug("Skipping provider seed %s (%s)", entry, exc)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------
    def add(self, provider: Provider | Dict[str, Any]) -> Provider:
        item = self._coerce(provider)
        if not item.id:
            raise ValueError("provider id is required")
        with self._lock:
            self._items[item.id] = item
            self._persist_locked()
        return item

    def get(self, provider_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._items.get(provider_id)
            return asdict(item) if item else None

    def remove(self, provider_id: str) -> bool:
        with self._lock:
            existed = provider_id in self._items
            self._items.pop(provider_id, None)
            if existed:
                self._persist_locked()
            return existed

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [asdict(item) for item in self._items.values()]

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _persist_locked(self) -> None:
        if not self._storage_path:
            return
        payload = {"providers": [asdict(item) for item in self._items.values()]}
        try:
            self._storage_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to persist provider registry: %s", exc)

    def _load_from_disk(self) -> None:
        if not self._storage_path or not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            providers = data.get("providers", [])
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Provider registry unreadable (%s); starting empty", exc)
            providers = []
        for entry in providers:
            try:
                item = self._coerce(entry)
            except Exception:
                continue
            if item.id:
                self._items[item.id] = item

    @staticmethod
    def _coerce(value: Provider | Dict[str, Any]) -> Provider:
        if isinstance(value, Provider):
            return value
        if not isinstance(value, dict):
            raise TypeError(f"unsupported provider payload: {value!r}")
        provider_id = str(value.get("id") or "").strip()
        if not provider_id:
            raise ValueError("provider id missing")
        kind = str(value.get("kind") or "custom").strip() or "custom"
        base = str(
            value.get("base") or value.get("base_url") or value.get("endpoint") or ""
        ).strip()
        meta = _coerce_meta(value.get("meta"))
        return Provider(id=provider_id, kind=kind, base=base, meta=meta)


def load_seed_from_config(
    paths: Optional[Iterable[str | Path]] = None,
) -> List[Dict[str, Any]]:
    """Load provider entries from optional JSON configs."""

    candidates: List[Path] = []
    if paths:
        for candidate in paths:
            candidates.append(Path(candidate).expanduser())
    else:
        candidates = [
            Path("config/comfyvn.json"),
            Path("comfyvn.json"),
        ]

    seeds: List[Dict[str, Any]] = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Skipping %s (%s)", path, exc)
            continue
        features = data.get("features") or {}
        if features and not bool(features.get("enable_compute", True)):
            LOGGER.debug("Compute disabled in %s", path)
            continue
        for entry in data.get("providers", []) or []:
            if isinstance(entry, dict):
                seeds.append(entry)
    return seeds


DEFAULT_STORAGE_PATH = Path("config/compute_providers.json")
_DEFAULT_REGISTRY: ProviderRegistry | None = None


def get_default_registry() -> ProviderRegistry:
    """Return a process-wide provider registry backed by the default storage path."""

    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = ProviderRegistry(
            storage_path=DEFAULT_STORAGE_PATH,
            seed=load_seed_from_config(),
        )
    return _DEFAULT_REGISTRY
