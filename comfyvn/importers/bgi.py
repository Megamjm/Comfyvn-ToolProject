from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.importers.base import DetectResult, PlanResult
from comfyvn.core.normalizer import normalize_tree

LOGGER = logging.getLogger(__name__)


class BGIImporter:
    id = "bgi"
    label = "BGI / Ethornell"

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        reasons: list[str] = []
        arc_files = list(root_path.glob("data*.arc"))
        org_files = list((root_path / "_bp").glob("*.org")) if (root_path / "_bp").exists() else []
        if arc_files:
            reasons.append(f"{len(arc_files)}x data*.arc")
        if org_files:
            reasons.append(f"{len(org_files)}x _bp/*.org")
        if (root_path / "bgi.exe").exists():
            reasons.append("bgi.exe")
        confidence = 0.0
        if arc_files:
            confidence += 0.5
        if org_files:
            confidence += 0.3
        if (root_path / "bgi.exe").exists():
            confidence += 0.2
        return DetectResult(engine=self.label, confidence=min(confidence, 0.9), reasons=reasons or ["generic"])

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Locate data*.arc archives and disassembled script trees (_bp/*.org).",
            "Collect converted assets (PNG/OGG) provided by the user.",
            "Normalize into comfyvn-pack with script control codes recorded in metadata.",
        ]
        warnings = [
            "BGI archives often require GARbro CLI or similar; we assume assets are already extracted.",
            "Maintain script ↔ voice linkage; many titles use numeric voice IDs.",
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
            "notes": ["BGI importer executed"],
        }
        LOGGER.info("Normalizing BGI project from %s -> %s", root_path, out_path)
        return normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
        )


__all__ = ["BGIImporter"]
