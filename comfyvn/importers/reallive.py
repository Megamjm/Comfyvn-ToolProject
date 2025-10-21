from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.importers.base import DetectResult, PlanResult
from comfyvn.core.normalizer import normalize_tree

LOGGER = logging.getLogger(__name__)


class RealLiveImporter:
    id = "reallive"
    label = "RealLive / Siglus"

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        reasons: list[str] = []
        if (root_path / "RealLive.exe").exists() or (root_path / "SiglusEngine.exe").exists():
            reasons.append("engine executable present")
        scene_pck = list(root_path.glob("Scene.pck"))
        if scene_pck:
            reasons.append("Scene.pck")
        script_files = list(root_path.glob("*.org")) + list(root_path.glob("*.ss"))
        if script_files:
            reasons.append(f"{len(script_files)}x script files")
        confidence = 0.0
        if reasons:
            confidence += 0.5
        if script_files:
            confidence += 0.3
        if scene_pck:
            confidence += 0.2
        return DetectResult(engine=self.label, confidence=min(confidence, 0.85), reasons=reasons or ["generic"])

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Identify Scene.pck and decompiled script files (.org/.ss).",
            "Ingest voice/BGM folders and retain script control opcodes.",
            "Write comfyvn-pack manifest with branchable scene graphs.",
        ]
        warnings = [
            "Siglus encryption requires user-provided tooling; importer expects pre-extracted assets.",
            "Ensure Gameexe.dat is left untouched—prefer overlay exports.",
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
            "notes": ["RealLive/Siglus importer executed"],
        }
        LOGGER.info("Normalizing RealLive/Siglus project from %s -> %s", root_path, out_path)
        result = normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
        )
        if result.warnings:
            LOGGER.warning("RealLive normalizer warnings:\n%s", "\n".join(result.warnings))
        return result


__all__ = ["RealLiveImporter"]
