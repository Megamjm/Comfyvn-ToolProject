from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.importers.base import DetectResult, PlanResult
from comfyvn.core.normalizer import normalize_tree

LOGGER = logging.getLogger(__name__)


class KiriKiriImporter:
    id = "kirikiri"
    label = "KiriKiri / KAG"

    def _scan(self, root_path: Path) -> tuple[list[str], int, int]:
        reasons: list[str] = []
        xp3_files = list(root_path.rglob("*.xp3"))
        if xp3_files:
            reasons.append(f"{len(xp3_files)}x .xp3 archives")
        ks_files = list(root_path.rglob("*.ks"))
        if ks_files:
            reasons.append(f"{len(ks_files)}x .ks scripts")
        if (root_path / "Config.tjs").exists():
            reasons.append("Config.tjs")
        return reasons, len(xp3_files), len(ks_files)

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        reasons, xp3_count, ks_count = self._scan(root_path)
        confidence = 0.0
        if xp3_count:
            confidence += 0.4
        if ks_count:
            confidence += 0.4
        if (root_path / "Config.tjs").exists():
            confidence += 0.2
        return DetectResult(engine="KiriKiri/KAG", confidence=min(confidence, 0.99), reasons=reasons or ["generic"])

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Identify base data.xp3 and patch.xp3 archives.",
            "Collect extracted folders (bg/, cg/, se/, voice/, scenario).",
            "Run optional hooks (arc_unpacker, tlg2png) to convert proprietary formats.",
            "Normalize to comfyvn-pack with overlay-friendly structure.",
        ]
        warnings = [
            "Respect patch.xp3 overlay semantics — prefer generating overlay packs instead of modifying base archives.",
            "Converted `.tlg` assets should be stored alongside originals for provenance.",
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
            "notes": ["KiriKiri importer executed"],
        }
        LOGGER.info("Normalizing KiriKiri project from %s -> %s", root_path, out_path)
        return normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
        )


__all__ = ["KiriKiriImporter"]
