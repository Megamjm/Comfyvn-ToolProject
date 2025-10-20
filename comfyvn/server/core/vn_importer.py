"""Utilities for importing packaged visual novels (.zip/.cvnpack/.pak).

This module is owned by the Importer chat (Phase 3) and is responsible for
unpacking VN bundles, copying their contents into the local data registry, and
emitting a structured summary that other systems (GUI, job queue, docs) can
consume.  The default behaviour writes into ``./data`` but honours the
``COMFYVN_DATA_ROOT`` override so tests and ephemeral runs can isolate their
artifacts.

The importer keeps the process intentionally defensive:

* all filesystem writes are gated through safe path checks to avoid zip-slip
  attacks;
* duplicate files are skipped (unless ``overwrite=True``) and reported;
* rich logging is emitted at INFO/DEBUG levels for troubleshooting;
* a JSON summary is persisted alongside the unpacked archive for auditability.

Example::

    from comfyvn.server.core.vn_importer import import_vn_package

    result = import_vn_package("~/Downloads/demo.cvnpack")
    print(result["scenes"])  # ["demo_intro"]

"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
_ALLOWED_ROOTS = {"scenes", "characters", "assets", "timelines", "licenses"}


class VNImportError(RuntimeError):
    """Raised when a VN package cannot be processed."""


@dataclass
class ImportSummary:
    """Structured summary emitted after a VN import completes."""

    import_id: str
    package_path: str
    manifest: Dict[str, object] | None = None
    scenes: List[str] = field(default_factory=list)
    characters: List[str] = field(default_factory=list)
    timelines: List[str] = field(default_factory=list)
    assets: List[str] = field(default_factory=list)
    licenses: List[Dict[str, object]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    data_root: str = field(default="")

    def to_dict(self) -> Dict[str, object]:
        return {
            "import_id": self.import_id,
            "package_path": self.package_path,
            "manifest": self.manifest or {},
            "scenes": self.scenes,
            "characters": self.characters,
            "timelines": self.timelines,
            "assets": self.assets,
            "licenses": self.licenses,
            "warnings": self.warnings,
            "data_root": self.data_root,
        }


def _resolve_data_root(explicit: Optional[Path] = None) -> Path:
    if explicit is not None:
        root = Path(explicit).expanduser().resolve()
    else:
        env = os.getenv("COMFYVN_DATA_ROOT")
        base = Path(env).expanduser() if env else Path("./data")
        root = base.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalise_member(path: str) -> Optional[Path]:
    """Normalise archive member names and drop leading package folders."""

    raw = Path(path)
    parts: List[str] = [p for p in raw.parts if p not in {"", ".", "./"}]
    if not parts:
        return None
    if any(p == ".." for p in parts):
        return None

    # peel off arbitrary top-level folders until we hit an allowed root
    idx = 0
    while idx < len(parts) - 1 and parts[idx].lower() not in _ALLOWED_ROOTS and parts[idx].lower() != "manifest.json":
        idx += 1
    trimmed = parts[idx:]
    if not trimmed:
        return None
    trimmed[0] = trimmed[0].lower()
    return Path(*trimmed)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_json_bytes(content: bytes, *, source: str, warnings: List[str]) -> Optional[Dict[str, object]]:
    try:
        text = content.decode("utf-8")
        return json.loads(text)
    except Exception as exc:  # pragma: no cover - defensive branch
        warnings.append(f"{source}: invalid JSON ({exc})")
        logger.warning("Failed to decode JSON from %s: %s", source, exc)
        return None


def _write_json(dest: Path, payload: Dict[str, object]) -> None:
    _ensure_parent(dest)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_binary(dest: Path, payload: bytes) -> None:
    _ensure_parent(dest)
    dest.write_bytes(payload)


def _disallow_overwrite(dest: Path, *, warnings: List[str]) -> bool:
    if dest.exists():
        warnings.append(f"skipped existing file: {dest}")
        logger.info("Skipping existing path during import: %s", dest)
        return True
    return False


def import_vn_package(
    package: str | Path,
    *,
    data_root: Optional[Path] = None,
    overwrite: bool = False,
) -> Dict[str, object]:
    """Import a packaged VN archive (.cvnpack/.zip/.pak) into the workspace.

    Parameters
    ----------
    package:
        Path to the archive on disk.
    data_root:
        Base directory for data writes. Defaults to ``./data`` (or
        ``COMFYVN_DATA_ROOT``). Tests can override this to avoid polluting the
        real workspace.
    overwrite:
        When ``True`` existing files will be replaced. Otherwise they are left
        untouched and a warning is emitted.
    """

    package_path = Path(package).expanduser().resolve()
    if not package_path.exists():
        raise VNImportError(f"package not found: {package_path}")
    if not zipfile.is_zipfile(package_path):
        raise VNImportError(f"unsupported package format: {package_path.suffix}")

    root = _resolve_data_root(data_root)
    import_id = f"{package_path.stem}-{int(time.time())}"
    import_root = root / "imports" / "vn" / import_id
    import_root.mkdir(parents=True, exist_ok=True)

    summary = ImportSummary(
        import_id=import_id,
        package_path=str(package_path),
        data_root=str(root),
    )

    logger.info("Starting VN import '%s' from %s", import_id, package_path)

    archive_copy = import_root / package_path.name
    shutil.copy2(package_path, archive_copy)

    scenes_dir = root / "scenes"
    characters_dir = root / "characters"
    timelines_dir = root / "timelines"
    assets_dir = root / "assets"
    licenses_dir = import_root / "licenses"

    manifest_path = import_root / "manifest.json"

    with zipfile.ZipFile(package_path, "r") as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            normalised = _normalise_member(member.filename)
            if normalised is None:
                summary.warnings.append(f"ignored path: {member.filename}")
                logger.debug("Ignoring archive member %s", member.filename)
                continue

            head = normalised.parts[0]
            payload = archive.read(member)

            if head == "manifest.json":
                manifest = _load_json_bytes(payload, source=member.filename, warnings=summary.warnings)
                if manifest:
                    summary.manifest = manifest
                    summary.licenses = list(manifest.get("licenses", [])) if isinstance(manifest.get("licenses"), list) else []
                    _write_json(manifest_path, manifest)
                    logger.debug("Loaded manifest from %s", member.filename)
                continue

            if head == "scenes":
                rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(member.filename).with_suffix("")
                dest = scenes_dir / rel
                if dest.suffix.lower() != ".json":
                    dest = dest.with_suffix(".json")
                if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                    continue
                data = _load_json_bytes(payload, source=str(normalised), warnings=summary.warnings)
                if data is None:
                    continue
                _write_json(dest, data)
                summary.scenes.append(dest.stem)
                logger.debug("Imported scene %s -> %s", rel, dest)
                continue

            if head == "characters":
                rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(member.filename).with_suffix("")
                dest = characters_dir / rel
                if dest.suffix.lower() != ".json":
                    dest = dest.with_suffix(".json")
                if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                    continue
                data = _load_json_bytes(payload, source=str(normalised), warnings=summary.warnings)
                if data is None:
                    continue
                _write_json(dest, data)
                summary.characters.append(dest.stem)
                logger.debug("Imported character %s -> %s", rel, dest)
                continue

            if head == "timelines":
                rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(member.filename).with_suffix("")
                dest = timelines_dir / rel
                if dest.suffix.lower() != ".json":
                    dest = dest.with_suffix(".json")
                if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                    continue
                data = _load_json_bytes(payload, source=str(normalised), warnings=summary.warnings)
                if data is None:
                    continue
                _write_json(dest, data)
                summary.timelines.append(dest.stem)
                logger.debug("Imported timeline %s -> %s", rel, dest)
                continue

            if head == "assets":
                rel = Path(*normalised.parts[1:])
                dest = assets_dir / rel
                if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                    continue
                _write_binary(dest, payload)
                summary.assets.append(str(rel))
                logger.debug("Imported asset %s -> %s", rel, dest)
                continue

            if head == "licenses":
                rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(member.filename)
                dest = licenses_dir / rel
                if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                    continue
                _write_binary(dest, payload)
                logger.debug("Stored license artifact %s -> %s", rel, dest)
                continue

            summary.warnings.append(f"unhandled member: {member.filename}")
            logger.debug("Unhandled archive member %s", member.filename)

    summary_path = import_root / "summary.json"
    _write_json(summary_path, summary.to_dict())
    logger.info(
        "VN import '%s' complete (%d scenes, %d characters, %d assets)",
        summary.import_id,
        len(summary.scenes),
        len(summary.characters),
        len(summary.assets),
    )

    # Soft fail if reindexing is unavailable to keep imports usable in minimal installs.
    try:  # pragma: no cover - optional integration
        from comfyvn.server.core import indexer

        indexer.reindex()
    except Exception as exc:
        summary.warnings.append(f"reindex failed: {exc}")
        logger.warning("Reindex after import failed: %s", exc)

    return summary.to_dict()


__all__ = ["import_vn_package", "VNImportError", "ImportSummary"]
