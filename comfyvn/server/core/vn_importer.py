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
* optional external extractors (arc_unpacker, etc.) can be registered and
  invoked when processing proprietary VN archive formats;
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
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from comfyvn.server.core.external_extractors import extractor_manager

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
    adapter: str = "generic"
    extractor: Optional[str] = None
    extractor_warning: Optional[str] = None
    scenes: List[str] = field(default_factory=list)
    characters: List[str] = field(default_factory=list)
    timelines: List[str] = field(default_factory=list)
    assets: List[str] = field(default_factory=list)
    licenses: List[Dict[str, object]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    data_root: str = field(default="")
    summary_path: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "import_id": self.import_id,
            "package_path": self.package_path,
            "manifest": self.manifest or {},
            "adapter": self.adapter,
            "extractor": self.extractor,
            "extractor_warning": self.extractor_warning,
            "scenes": self.scenes,
            "characters": self.characters,
            "timelines": self.timelines,
            "assets": self.assets,
            "licenses": self.licenses,
            "warnings": self.warnings,
            "data_root": self.data_root,
            "summary_path": self.summary_path,
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


def _infer_adapter(manifest: Optional[Dict[str, object]], members: Iterable[str]) -> str:
    manifest_engine = str(manifest.get("engine") or "").lower() if manifest else ""
    if "renpy" in manifest_engine:
        return "renpy"
    if manifest and any(k.lower().startswith("renpy") for k in manifest.keys()):
        return "renpy"

    for name in members:
        lower = name.lower()
        if lower.endswith(".rpy") or "/game/" in lower or lower.startswith("game/"):
            return "renpy"
    return "generic"


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


def _entries_from_zip(package_path: Path) -> List[tuple[str, bytes]]:
    entries: List[tuple[str, bytes]] = []
    with zipfile.ZipFile(package_path, "r") as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            entries.append((member.filename, archive.read(member)))
    return entries


def _entries_from_extractor(tool_name: str, package_path: Path) -> tuple[List[tuple[str, bytes]], str, Optional[str]]:
    tool = extractor_manager.get(tool_name)
    if not tool:
        raise VNImportError(f"extractor '{tool_name}' not registered")

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        try:
            extractor_manager.invoke(tool_name, package_path, output_dir=output_dir)
        except Exception as exc:  # pragma: no cover - defensive
            raise VNImportError(f"extractor '{tool_name}' failed: {exc}") from exc

        entries: List[tuple[str, bytes]] = []
        for file_path in output_dir.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(output_dir).as_posix()
                entries.append((rel, file_path.read_bytes()))
    warning = tool.warning if tool.warning else None
    return entries, tool.name, warning


def _gather_entries(package_path: Path, *, tool_hint: Optional[str] = None) -> tuple[List[tuple[str, bytes]], Optional[str], Optional[str]]:
    if tool_hint:
        return _entries_from_extractor(tool_hint, package_path)
    if zipfile.is_zipfile(package_path):
        return _entries_from_zip(package_path), None, None
    tool = extractor_manager.resolve_for_extension(package_path.suffix)
    if tool:
        entries, _, warning = _entries_from_extractor(tool.name, package_path)
        return entries, tool.name, warning
    raise VNImportError(f"unsupported package format: {package_path.suffix}")


def import_vn_package(
    package: str | Path,
    *,
    data_root: Optional[Path] = None,
    overwrite: bool = False,
    tool: Optional[str] = None,
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
    tool:
        Optional extractor name to force usage of a registered external tool
        (e.g., ``arc_unpacker``). When omitted we auto-detect based on file
        extension and fall back to native zip handling.
    """

    package_path = Path(package).expanduser().resolve()
    if not package_path.exists():
        raise VNImportError(f"package not found: {package_path}")
    entries, extractor_name, extractor_warning = _gather_entries(package_path, tool_hint=tool)

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

    seen_member_names: List[str] = []

    for raw_name, payload in entries:
        normalised = _normalise_member(raw_name)
        if normalised is None:
            summary.warnings.append(f"ignored path: {raw_name}")
            logger.debug("Ignoring archive member %s", raw_name)
            continue

        head = normalised.parts[0]
        seen_member_names.append(raw_name)

        if head == "manifest.json":
            manifest = _load_json_bytes(payload, source=raw_name, warnings=summary.warnings)
            if manifest:
                summary.manifest = manifest
                summary.licenses = list(manifest.get("licenses", [])) if isinstance(manifest.get("licenses"), list) else []
                _write_json(manifest_path, manifest)
                logger.debug("Loaded manifest from %s", raw_name)
            continue

        if head == "scenes":
            rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(raw_name).with_suffix("")
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
            rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(raw_name).with_suffix("")
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
            rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(raw_name).with_suffix("")
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
            rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(raw_name)
            dest = licenses_dir / rel
            if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                continue
            _write_binary(dest, payload)
            logger.debug("Stored license artifact %s -> %s", rel, dest)
            continue

        summary.warnings.append(f"unhandled member: {raw_name}")
        logger.debug("Unhandled archive member %s", raw_name)

    summary_path = import_root / "summary.json"
    summary.summary_path = summary_path.as_posix()
    summary.adapter = _infer_adapter(summary.manifest, seen_member_names)
    summary.extractor = extractor_name
    if extractor_warning:
        summary.extractor_warning = extractor_warning
        summary.warnings.append(extractor_warning)
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
