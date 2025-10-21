from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PACKAGE_ROOT = Path(__file__).resolve().parent
PROVIDERS_PATH = PACKAGE_ROOT / "providers.json"
NODESET_LOCK_PATH = PACKAGE_ROOT / "nodeset.lock.json"


@dataclass(slots=True)
class ProviderPack:
    """Pinned node pack in the canonical registry."""

    name: str
    repo: str
    commit: str
    category: Iterable[str] = field(default_factory=tuple)


@dataclass(slots=True)
class ProviderCatalog:
    """Representation of the provider template shipped with the repo."""

    node_packs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    models: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def load_providers_template(path: Path = PROVIDERS_PATH) -> ProviderCatalog:
    """Load the canonical provider registry template."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProviderCatalog(
        node_packs=data.get("nodePacks") or {},
        models=data.get("models") or {},
    )


def load_nodeset_lock(path: Path = NODESET_LOCK_PATH) -> List[ProviderPack]:
    """Return the pinned nodeset lock entries."""
    data = json.loads(path.read_text(encoding="utf-8"))
    packs: List[ProviderPack] = []
    for row in data.get("packs") or []:
        packs.append(
            ProviderPack(
                name=row.get("name", ""),
                repo=row.get("repo", ""),
                commit=row.get("commit", ""),
                category=row.get("category") or [],
            )
        )
    return packs


__all__ = [
    "NODESET_LOCK_PATH",
    "PROVIDERS_PATH",
    "ProviderCatalog",
    "ProviderPack",
    "load_nodeset_lock",
    "load_providers_template",
]

