from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.importers.base import DetectResult, PlanResult
from comfyvn.core.normalizer import normalize_tree

LOGGER = logging.getLogger(__name__)


class YuRISImporter:
    id = "yuris"
    label = "Yu-RIS"

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        reasons: list[str] = []
        ypf_files = list(root_path.glob("*.ypf"))
        if ypf_files:
            reasons.append(f"{len(ypf_files)}x .ypf archives")
        ybn_files = list(root_path.glob("yst*.ybn"))
        if ybn_files:
            reasons.append(f"{len(ybn_files)}x YST scripts")
        confidence = 0.0
        if ypf_files:
            confidence += 0.5
        if ybn_files:
            confidence += 0.4
        return DetectResult(engine=self.label, confidence=min(confidence, 0.9), reasons=reasons or ["generic"])

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Collect .ypf archives or previously extracted asset folders.",
            "Parse yst*.ybn script metadata for voice/line mapping (requires user-provided tooling).",
            "Normalize media assets to comfyvn-pack layout.",
        ]
        warnings = [
            "Yu-RIS scripts may require proprietary tools to decode; importer expects already extracted text.",
            "Voice files often mirror script IDs; maintain mapping in manifest.",
        ]
        return PlanResult(steps=steps, warnings=warnings)

    def import_pack(
        self,
        root: Path | str,
        out_dir: Path | str,
        *,
        hooks: Optional[Dict[str, str]] = None,
    ) -> Path:
        root_path = Path(root)
        out_path = Path(out_dir)
        manifest = {
            "engine": self.label,
            "sources": {"root": str(root_path.resolve()), "hooks": hooks or {}},
            "notes": ["Yu-RIS importer executed"],
        }
        LOGGER.info("Normalizing Yu-RIS project from %s -> %s", root_path, out_path)
        return normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
        )


__all__ = ["YuRISImporter"]
