from __future__ import annotations

# comfyvn/core/extension_store.py
from dataclasses import dataclass
from typing import Iterable, List

from PySide6.QtGui import QAction

from comfyvn.market import MarketCatalog


@dataclass
class CatalogItem:
    id: str
    name: str
    summary: str
    trust: str
    package: str | None
    permissions: List[str]
    hooks: List[str]
    source: str


_CATALOG = MarketCatalog()


def _convert(items: Iterable[dict]) -> List[CatalogItem]:
    converted: List[CatalogItem] = []
    for raw in items:
        converted.append(
            CatalogItem(
                id=str(raw.get("id") or ""),
                name=str(raw.get("name") or ""),
                summary=str(raw.get("summary") or raw.get("description") or ""),
                trust=str(raw.get("trust") or "unverified"),
                package=str(raw.get("package") or "") or None,
                permissions=list(raw.get("permissions") or []),
                hooks=list(raw.get("hooks") or []),
                source=str(raw.get("source") or "catalog"),
            )
        )
    return converted


def list_catalog() -> List[CatalogItem]:
    return _convert(entry.to_payload() for entry in _CATALOG.entries())


def refresh_catalog() -> List[CatalogItem]:
    _CATALOG.reload()
    return list_catalog()


CATALOG = list_catalog()
