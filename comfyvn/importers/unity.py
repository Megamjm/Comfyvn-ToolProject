from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.core.normalizer import normalize_tree
from comfyvn.importers.base import DetectResult, PlanResult

LOGGER = logging.getLogger(__name__)


class UnityVNImporter:
    id = "unity_vn"
    label = "Unity-based VN"

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        reasons: list[str] = []
        data_dirs = list(root_path.glob("*_Data"))
        asset_files = list(root_path.rglob("*.assets"))
        bundle_files = list(root_path.rglob("*.bundle")) + list(
            root_path.rglob("*.unity3d")
        )
        if data_dirs:
            reasons.append(f"{len(data_dirs)}x *_Data folders")
        if asset_files:
            reasons.append(f"{len(asset_files)}x .assets files")
        if bundle_files:
            reasons.append(f"{len(bundle_files)}x AssetBundles")
        confidence = 0.0
        if data_dirs:
            confidence += 0.5
        if asset_files or bundle_files:
            confidence += 0.3
        return DetectResult(
            engine=self.label,
            confidence=min(confidence, 0.8),
            reasons=reasons or ["generic"],
        )

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Expect user-exported textures/audio (PNG/OGG/WAV) from Unity assets.",
            "Ingest AssetBundles when provided and record GUID mapping if available.",
            "Normalize extracted media into comfyvn-pack; store bundle metadata under raw/ for traceability.",
        ]
        warnings = [
            "Importer does not extract Unity AssetBundles — user must run UnityPy/AssetStudio beforehand.",
            "Preserve original file names to maintain compatibility with script references.",
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
            "notes": ["Unity VN importer executed"],
        }
        LOGGER.info("Normalizing Unity VN project from %s -> %s", root_path, out_path)
        result = normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
        )
        if result.warnings:
            LOGGER.warning(
                "Unity VN normalizer warnings:\n%s", "\n".join(result.warnings)
            )
        return result


__all__ = ["UnityVNImporter"]
