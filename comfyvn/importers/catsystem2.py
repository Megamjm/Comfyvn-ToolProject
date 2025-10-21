from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.core.normalizer import normalize_tree
from comfyvn.importers.base import DetectResult, PlanResult

LOGGER = logging.getLogger(__name__)


class CatSystem2Importer:
    id = "catsystem2"
    label = "CatSystem2"

    _ARCHIVE_EXTS = {".int", ".dat"}
    _SCRIPT_EXTS = {".cst", ".fes", ".anm"}
    _IMAGE_EXTS = {".hg2", ".hg3"}

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        reasons: list[str] = []
        confidence = 0.0
        for ext in self._ARCHIVE_EXTS:
            files = list(root_path.glob(f"*{ext}"))
            if files:
                reasons.append(f"{len(files)}x {ext} archives")
                confidence += 0.3
        for ext in self._SCRIPT_EXTS:
            scripts = list(root_path.glob(f"*{ext}"))
            if scripts:
                reasons.append(f"{len(scripts)}x {ext} scripts")
                confidence += 0.2
        image_hits = []
        for ext in self._IMAGE_EXTS:
            image_hits.extend(root_path.glob(f"*{ext}"))
        if image_hits:
            reasons.append(f"{len(image_hits)}x proprietary images (.hg2/.hg3)")
            confidence += 0.2
        return DetectResult(
            engine=self.label,
            confidence=min(confidence, 0.85),
            reasons=reasons or ["generic"],
        )

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Identify CatSystem2 archives (.int/.dat) and extracted folders.",
            "Convert .hg2/.hg3 images to PNG when user supplies conversion hook.",
            "Parse .cst scene scripts for line/voice mapping if available.",
        ]
        warnings = [
            "Requires user-supplied converter (e.g., GARbro CLI) for proprietary image formats.",
            "Scene scripts may include control opcodes; preserve them as manifest tags.",
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
            "notes": ["CatSystem2 importer executed"],
        }
        LOGGER.info("Normalizing CatSystem2 project from %s -> %s", root_path, out_path)
        result = normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
        )
        if result.warnings:
            LOGGER.warning(
                "CatSystem2 normalizer warnings:\n%s", "\n".join(result.warnings)
            )
        return result


__all__ = ["CatSystem2Importer"]
