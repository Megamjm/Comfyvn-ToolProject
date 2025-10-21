from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.importers.base import DetectResult, PlanResult
from comfyvn.core.normalizer import normalize_tree

LOGGER = logging.getLogger(__name__)


class TyranoImporter:
    id = "tyrano"
    label = "TyranoScript"

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        data_dir = root_path / "data"
        reasons: list[str] = []
        confidence = 0.0
        if data_dir.exists():
            reasons.append("data/")
            confidence += 0.5
        scenario_dir = data_dir / "scenario"
        if scenario_dir.exists() and list(scenario_dir.glob("*.ks")):
            reasons.append("scenario/*.ks")
            confidence += 0.3
        for sub in ["bgimage", "fgimage", "sound"]:
            if (data_dir / sub).exists():
                reasons.append(f"data/{sub}/")
                confidence += 0.1
        return DetectResult(engine=self.label, confidence=min(confidence, 0.95), reasons=reasons or ["generic"])

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Copy data/scenario/*.ks, fgimage/, bgimage/, sound/ into comfyvn-pack",
            "Preserve Tyrano tags intact inside text manifests.",
        ]
        warnings = [
            "Importer assumes plain data/ layout (desktop/web export).",
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
            "notes": ["Tyrano importer executed"],
        }
        LOGGER.info("Normalizing Tyrano project from %s -> %s", root_path, out_path)
        result = normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
            include_dirs=["data"],
        )
        if result.warnings:
            LOGGER.warning("Tyrano normalizer warnings:\n%s", "\n".join(result.warnings))
        return result


__all__ = ["TyranoImporter"]
