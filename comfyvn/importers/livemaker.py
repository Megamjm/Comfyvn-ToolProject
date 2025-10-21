from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.core.normalizer import normalize_tree
from comfyvn.importers.base import DetectResult, PlanResult

LOGGER = logging.getLogger(__name__)


class LiveMakerImporter:
    id = "livemaker"
    label = "LiveMaker"

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        reasons: list[str] = []
        lmd_files = list(root_path.glob("*.lmd")) + list(root_path.glob("*.lwv"))
        if lmd_files:
            reasons.append(f"{len(lmd_files)}x LiveMaker archives")
        extracted = (root_path / "data").exists() or (root_path / "scenario").exists()
        if extracted:
            reasons.append("extracted data folder")
        confidence = 0.0
        if lmd_files:
            confidence += 0.5
        if extracted:
            confidence += 0.3
        return DetectResult(
            engine=self.label,
            confidence=min(confidence, 0.8),
            reasons=reasons or ["generic"],
        )

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Expect user to extract LiveMaker archive via pylivemaker or similar.",
            "Normalize extracted assets (bg/, char/, scenario) into comfyvn-pack.",
            "Record node graph metadata (if available) in scene manifest.",
        ]
        warnings = [
            "LiveMaker archives often compress aggressively; importer uses already-extracted data."
        ]
        return PlanResult(steps=steps, warnings=warnings)

    def import_pack(
        self,
        root: Path | str,
        out_dir: Path | str,
        *,
        hooks: Optional[Dict[str, str]] = None,
    ):
        root_path = Path(root)
        out_path = Path(out_dir)
        manifest = {
            "engine": self.label,
            "sources": {"root": str(root_path.resolve()), "hooks": hooks or {}},
            "notes": ["LiveMaker importer executed"],
        }
        LOGGER.info("Normalizing LiveMaker project from %s -> %s", root_path, out_path)
        result = normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
        )
        if result.warnings:
            LOGGER.warning(
                "LiveMaker normalizer warnings:\n%s", "\n".join(result.warnings)
            )
        return result


__all__ = ["LiveMakerImporter"]
