"""
Common utilities shared by VN pack archive adapters.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import ClassVar, Dict, Iterable, List, Optional, Tuple

from comfyvn.importers import ALL_IMPORTERS
from comfyvn.importers.base import DetectResult, PlanResult


def _serialize_detect(importer_id: str, importer_label: str, result: DetectResult):
    payload = {
        "id": importer_id,
        "label": importer_label,
        "engine": result.engine,
        "confidence": result.confidence,
        "reasons": list(result.reasons),
    }
    return payload


def _serialize_plan(plan: PlanResult) -> Dict[str, object]:
    data = asdict(plan) if is_dataclass(plan) else {}
    if not data:
        data = {"steps": plan.steps, "warnings": plan.warnings}
    data.setdefault("steps", [])
    data.setdefault("warnings", [])
    return data


def _analyze_importers(root: Path) -> Dict[str, object]:
    root = Path(root)
    detections: List[Dict[str, object]] = []
    best: Optional[Tuple[object, DetectResult]] = None

    for importer in ALL_IMPORTERS:
        try:
            detect_result = importer.detect(root)
        except Exception:
            continue
        payload = _serialize_detect(importer.id, importer.label, detect_result)
        detections.append(payload)
        if best is None or detect_result.confidence > best[1].confidence:
            best = (importer, detect_result)

    detections.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
    preview: Dict[str, object] = {
        "engine": None,
        "detections": detections[:10],
    }
    if best and best[1].confidence > 0:
        importer, detect_result = best
        engine_payload = _serialize_detect(importer.id, importer.label, detect_result)
        try:
            plan = importer.plan(root)
        except Exception:
            plan = None
        if isinstance(plan, PlanResult):
            engine_payload["plan"] = _serialize_plan(plan)
        preview["engine"] = engine_payload
    return preview


class BaseAdapter:
    """
    Minimal interface for packaged VN archive handlers.

    Subclasses should implement ``list_contents`` and ``extract`` while
    optionally overriding ``map_scene_graph`` to provide richer previews.
    """

    exts: ClassVar[tuple[str, ...]] = ()

    def __init__(self, path: Path | str):
        self.path = Path(path)

    @classmethod
    def detect(cls, path: Path | str) -> bool:
        candidate = Path(path)
        return candidate.suffix.lower() in cls.exts

    def list_contents(self) -> List[Dict[str, object]]:
        raise NotImplementedError

    def extract(self, out_dir: Path) -> Iterable[Path]:
        raise NotImplementedError

    def map_scene_graph(self, extracted_root: Path) -> Dict[str, object]:
        preview = _analyze_importers(Path(extracted_root))
        preview.setdefault("scenes", [])
        preview.setdefault("assets", [])
        preview.setdefault(
            "notes", "scene graph mapping available after full normalization"
        )
        return preview
