from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from comfyvn.importers.base import DetectResult, Importer, PlanResult
from comfyvn.importers.renpy_setup import ensure_renpy_sdk, get_renpy_executable
from comfyvn.core.normalizer import normalize_tree

LOGGER = logging.getLogger(__name__)


class RenpyImporter:
    id = "renpy"
    label = "Ren'Py"

    _SCRIPT_EXTS = {".rpy", ".rpyc"}
    _ARCHIVE_EXT = ".rpa"

    def detect(self, root: Path | str) -> DetectResult:
        root_path = Path(root)
        reasons: list[str] = []
        game_dir = root_path / "game"
        if game_dir.exists():
            reasons.append("game/")
        archives = list(game_dir.glob(f"*{self._ARCHIVE_EXT}"))
        if archives:
            reasons.append(f"{len(archives)}x {self._ARCHIVE_EXT}")
        scripts = []
        for ext in self._SCRIPT_EXTS:
            scripts.extend(game_dir.glob(f"*{ext}"))
        if scripts:
            reasons.append(f"{len(scripts)}x script files")
        confidence = 0.0
        if game_dir.exists():
            confidence += 0.5
        if archives:
            confidence += 0.3
        if scripts:
            confidence += 0.2
        return DetectResult(engine="Ren'Py", confidence=min(confidence, 0.99), reasons=reasons or ["generic"])

    def plan(self, root: Path | str) -> PlanResult:
        steps = [
            "Collect loose assets under game/ (images, audio, scripts).",
            "Optionally extract .rpa archives when hooks['unrpa'] or hooks['rpatool'] is provided.",
            "Ensure Ren'Py SDK is installed (downloaded automatically if missing).",
            "Normalize assets into comfyvn-pack manifest with stable IDs.",
        ]
        warnings = [
            "Ren'Py archives (.rpa) require user-supplied tooling (unrpa/rpatool).",
            "Preserve text interpolation markers and style tags.",
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
        renpy_home = ensure_renpy_sdk()
        LOGGER.info("Using Ren'Py SDK at %s", renpy_home)
        renpy_exec = get_renpy_executable(renpy_home)

        manifest = {
            "engine": self.label,
            "sources": {
                "root": str(root_path.resolve()),
                "hooks": hooks or {},
                "renpy_home": str(renpy_home),
            },
            "notes": ["Ren'Py importer executed", f"Ren'Py SDK ensured at {renpy_home}"],
        }
        if renpy_exec:
            manifest["sources"]["renpy_executable"] = str(renpy_exec)

        LOGGER.info("Normalizing Ren'Py project from %s -> %s", root_path, out_path)
        return normalize_tree(
            root_path,
            out_path,
            engine=self.label,
            manifest_patch=manifest,
            hooks=hooks or {},
        )


__all__ = ["RenpyImporter"]
