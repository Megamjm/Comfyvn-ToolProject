from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.importers.base import DetectResult, PlanResult
from comfyvn.core.normalizer import normalize_tree

LOGGER = logging.getLogger(__name__)


class NscripterImporter:
    id = "nscripter"
    label = "NScripter / ONScripter"

    _ARCHIVE_EXTS = {".nsa", ".ns2", ".sar"}
    _SCRIPT_FILES = {"nscript.dat", "0.txt"}

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        reasons: list[str] = []
        confidence = 0.0
        for script in self._SCRIPT_FILES:
            if (root_path / script).exists():
                reasons.append(script)
                confidence += 0.4
        archives = []
        for ext in self._ARCHIVE_EXTS:
            archives.extend(root_path.glob(f"*{ext}"))
        if archives:
            reasons.append(f"{len(archives)}x NSA/NS2 archives")
            confidence += 0.4
        media_dir = any((root_path / sub).exists() for sub in ["voice", "bgm", "bgimage", "music"])
        if media_dir:
            reasons.append("media folders present")
            confidence += 0.1
        return DetectResult(engine=self.label, confidence=min(confidence, 0.95), reasons=reasons or ["generic"])

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Scan for nscript.dat/0.txt and archive (.nsa/.ns2/.sar) contents.",
            "Decode Shift-JIS text and maintain control codes.",
            "Extract loose media folders for normalization.",
        ]
        warnings = [
            "External tools (e.g., nsadec) must be supplied by the user for encrypted archives.",
            "Large bitmap assets may need conversion to PNG/JPG during normalization.",
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
            "notes": ["NScripter importer executed"],
        }
        LOGGER.info("Normalizing NScripter project from %s -> %s", root_path, out_path)
        return normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
        )


__all__ = ["NscripterImporter"]
