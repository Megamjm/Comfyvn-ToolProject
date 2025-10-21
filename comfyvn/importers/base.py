"""
Importer infrastructure — shared base classes and helper types.

Each importer recognises a specific VN engine layout, emits detection metadata,
and (optionally) produces a normalized ``comfyvn-pack`` via the normalizer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol, runtime_checkable

from comfyvn.core.normalizer import NormalizerResult


@dataclass
class DetectResult:
    engine: str
    confidence: float
    reasons: List[str]


@dataclass
class PlanResult:
    steps: List[str]
    warnings: List[str]


@runtime_checkable
class Importer(Protocol):
    """Protocol shared by importer implementations."""

    id: str
    label: str

    def detect(self, root: Path | str) -> DetectResult:
        ...

    def plan(self, root: Path | str) -> PlanResult:
        ...

    def import_pack(
        self,
        root: Path | str,
        out_dir: Path | str,
        *,
        hooks: Optional[Dict[str, str]] = None,
    ) -> NormalizerResult:
        ...


def _stringify_paths(paths: Iterable[Path]) -> List[str]:
    return [str(p) for p in paths]


__all__ = ["DetectResult", "PlanResult", "Importer", "_stringify_paths"]
