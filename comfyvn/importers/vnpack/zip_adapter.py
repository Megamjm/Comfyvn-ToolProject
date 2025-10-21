"""
Zip-based VN pack adapter.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List

from comfyvn.importers.vnpack.base import BaseAdapter


def _safe_member_path(name: str) -> Path | None:
    raw = Path(name)
    parts = []
    for part in raw.parts:
        if part in {"", ".", "./"}:
            continue
        if part == "..":
            return None
        parts.append(part)
    if not parts:
        return None
    return Path(*parts)


class ZipAdapter(BaseAdapter):
    """Adapter for zip-based VN packs (.zip / .cvnpack)."""

    exts = (".zip", ".cvnpack")

    def list_contents(self) -> List[Dict[str, object]]:
        listing: List[Dict[str, object]] = []
        with zipfile.ZipFile(self.path, "r") as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                entry = {
                    "path": info.filename,
                    "size": info.file_size,
                    "compressed": info.compress_size,
                    "is_dir": info.is_dir(),
                }
                listing.append(entry)
        return listing

    def extract(self, out_dir: Path) -> Iterable[Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        extracted: List[Path] = []
        with zipfile.ZipFile(self.path, "r") as archive:
            for info in archive.infolist():
                member_path = _safe_member_path(info.filename)
                if member_path is None:
                    continue
                target = out_dir / member_path
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted.append(target)
        return extracted

    def map_scene_graph(self, extracted_root: Path) -> Dict[str, object]:
        extracted_root = Path(extracted_root)
        preview = super().map_scene_graph(extracted_root)
        scripts: List[str] = []
        assets: List[str] = []
        if extracted_root.exists():
            for path in extracted_root.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(extracted_root).as_posix()
                lower = rel.lower()
                if lower.endswith((".rpy", ".rpyc", ".ks", ".json")):
                    scripts.append(rel)
                elif lower.endswith(
                    (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ogg", ".mp3", ".wav")
                ):
                    assets.append(rel)
        preview["scenes"] = scripts[:25]
        preview["assets"] = assets[:25]
        preview["notes"] = (
            "Detected via importer registry; file lists truncated for preview"
        )
        return preview
