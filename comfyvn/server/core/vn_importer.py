"""Utilities for importing packaged visual novels (.zip/.cvnpack/.pak)."""

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

from comfyvn.core.normalizer import NormalizerResult, normalize_tree
from comfyvn.importers import ALL_IMPORTERS, get_importer
from comfyvn.server.core.external_extractors import extractor_manager
from comfyvn.server.core.translation_pipeline import build_translation_bundle, plan_remix_tasks

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
    pack_path: Optional[str] = None
    normalizer: Dict[str, object] = field(default_factory=dict)
    detections: List[Dict[str, object]] = field(default_factory=list)
    translation: Dict[str, object] = field(default_factory=dict)
    remix: Dict[str, object] = field(default_factory=dict)

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
            "pack_path": self.pack_path,
            "normalizer": self.normalizer,
            "detections": self.detections,
            "translation": self.translation,
            "remix": self.remix,
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


def _sanitize_member(path: str) -> Optional[Path]:
    raw = Path(path)
    parts = [p for p in raw.parts if p not in {"", ".", "./"}]
    if not parts or any(part == ".." for part in parts):
        return None
    return Path(*parts)


def _normalise_member(path: str) -> Optional[Path]:
    """Normalise archive member names and drop leading package folders."""

    raw = Path(path)
    parts: List[str] = [p for p in raw.parts if p not in {"", ".", "./"}]
    if not parts:
        return None
    if any(p == ".." for p in parts):
        return None

    idx = 0
    while (
        idx < len(parts) - 1
        and parts[idx].lower() not in _ALLOWED_ROOTS
        and parts[idx].lower() != "manifest.json"
    ):
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


def _detect_importer(stage_root: Path, manifest: Optional[Dict[str, object]]):
    detections: List[Dict[str, object]] = []
    engine_hint = str(manifest.get("engine") or "").lower() if manifest else ""
    if engine_hint:
        try:
            importer = get_importer(engine_hint)
            detections.append(
                {"id": importer.id, "label": importer.label, "confidence": 1.0, "reasons": ["manifest hint"]}
            )
            return importer, detections
        except KeyError:
            detections.append(
                {"id": engine_hint, "label": engine_hint, "confidence": 0.0, "reasons": ["unknown manifest engine"]}
            )

    for importer in ALL_IMPORTERS:
        try:
            det = importer.detect(stage_root)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Engine detect failed for %s: %s", importer.id, exc)
            continue
        detections.append(
            {
                "id": importer.id,
                "label": importer.label,
                "confidence": det.confidence,
                "reasons": det.reasons,
            }
        )

    detections.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
    if detections and detections[0].get("confidence", 0.0) > 0:
        best_id = detections[0]["id"]
        try:
            importer = get_importer(best_id)
            return importer, detections
        except KeyError:
            pass
    return None, detections


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
    """Import a packaged VN archive (.cvnpack/.zip/.pak) into the workspace."""

    package_path = Path(package).expanduser().resolve()
    if not package_path.exists():
        raise VNImportError(f"package not found: {package_path}")
    entries, extractor_name, extractor_warning = _gather_entries(package_path, tool_hint=tool)

    root = _resolve_data_root(data_root)
    import_id = f"{package_path.stem}-{int(time.time())}"
    import_root = root / "imports" / "vn" / import_id
    import_root.mkdir(parents=True, exist_ok=True)

    summary = ImportSummary(import_id=import_id, package_path=str(package_path), data_root=str(root))

    logger.info("Starting VN import '%s' from %s", import_id, package_path)

    archive_copy = import_root / package_path.name
    shutil.copy2(package_path, archive_copy)

    stage_root = import_root / "stage"
    stage_root.mkdir(parents=True, exist_ok=True)

    staged_entries: List[tuple[Path, Path]] = []
    for raw_name, payload in entries:
        safe_rel = _sanitize_member(raw_name)
        if safe_rel is None:
            summary.warnings.append(f"ignored unsafe member: {raw_name}")
            logger.debug("Skipping unsafe archive member %s", raw_name)
            continue
        stage_path = stage_root / safe_rel
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        stage_path.write_bytes(payload)
        staged_entries.append((safe_rel, stage_path))

    scenes_dir = root / "scenes"
    characters_dir = root / "characters"
    timelines_dir = root / "timelines"
    assets_dir = root / "assets"
    licenses_dir = import_root / "licenses"
    manifest_path = import_root / "manifest.json"

    seen_member_names: List[str] = []
    original_manifest: Optional[Dict[str, object]] = None

    for safe_rel, stage_path in staged_entries:
        normalised = _normalise_member(safe_rel.as_posix())
        if normalised is None:
            summary.warnings.append(f"ignored path: {safe_rel.as_posix()}")
            logger.debug("Ignoring archive member %s", safe_rel)
            continue

        head = normalised.parts[0]
        seen_member_names.append(safe_rel.as_posix())

        if head == "manifest.json":
            manifest = _load_json_bytes(stage_path.read_bytes(), source=safe_rel.as_posix(), warnings=summary.warnings)
            if manifest:
                original_manifest = manifest
                summary.manifest = manifest
                summary.licenses = list(manifest.get("licenses", [])) if isinstance(manifest.get("licenses"), list) else []
                _write_json(manifest_path, manifest)
                logger.debug("Loaded manifest from %s", safe_rel)
            continue

        if head == "scenes":
            rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(safe_rel).with_suffix("")
            dest = scenes_dir / rel
            if dest.suffix.lower() != ".json":
                dest = dest.with_suffix(".json")
            if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                continue
            data = _load_json_bytes(stage_path.read_bytes(), source=str(normalised), warnings=summary.warnings)
            if data is None:
                continue
            _write_json(dest, data)
            summary.scenes.append(dest.stem)
            logger.debug("Imported scene %s -> %s", rel, dest)
            continue

        if head == "characters":
            rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(safe_rel).with_suffix("")
            dest = characters_dir / rel
            if dest.suffix.lower() != ".json":
                dest = dest.with_suffix(".json")
            if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                continue
            data = _load_json_bytes(stage_path.read_bytes(), source=str(normalised), warnings=summary.warnings)
            if data is None:
                continue
            _write_json(dest, data)
            summary.characters.append(dest.stem)
            logger.debug("Imported character %s -> %s", rel, dest)
            continue

        if head == "timelines":
            rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(safe_rel).with_suffix("")
            dest = timelines_dir / rel
            if dest.suffix.lower() != ".json":
                dest = dest.with_suffix(".json")
            if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                continue
            data = _load_json_bytes(stage_path.read_bytes(), source=str(normalised), warnings=summary.warnings)
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
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage_path, dest)
            summary.assets.append(str(rel))
            logger.debug("Imported asset %s -> %s", rel, dest)
            continue

        if head == "licenses":
            rel = Path(*normalised.parts[1:]) if len(normalised.parts) > 1 else Path(safe_rel)
            dest = licenses_dir / rel
            if not overwrite and _disallow_overwrite(dest, warnings=summary.warnings):
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage_path, dest)
            logger.debug("Stored license artifact %s -> %s", rel, dest)
            continue

        summary.warnings.append(f"unhandled member: {safe_rel.as_posix()}")
        logger.debug("Unhandled archive member %s", safe_rel)

    summary.extractor = extractor_name
    if extractor_warning:
        summary.extractor_warning = extractor_warning
        summary.warnings.append(extractor_warning)

    importer, detections = _detect_importer(stage_root, original_manifest or summary.manifest)
    summary.detections = detections
    normalizer_result: Optional[NormalizerResult] = None
    adapter_id: Optional[str] = importer.id if importer else None

    try:
        if importer:
            logger.info("Running %s importer for %s", importer.id, import_id)
            normalizer_result = importer.import_pack(stage_root, import_root)
        else:
            fallback_adapter = _infer_adapter(original_manifest, seen_member_names)
            adapter_id = fallback_adapter
            fallback_engine = fallback_adapter if fallback_adapter != "generic" else "Generic"
            fallback_patch: Dict[str, object] = {
                "sources": {"root": str(stage_root)},
                "notes": ["Generic normalizer fallback"],
            }
            if original_manifest:
                fallback_patch["original_manifest"] = original_manifest
            normalizer_result = normalize_tree(stage_root, import_root, engine=fallback_engine, manifest_patch=fallback_patch)
    except Exception as exc:
        summary.warnings.append(f"normalizer failed: {exc}")
        logger.warning("Normalizer execution failed during import %s: %s", import_id, exc, exc_info=True)
        normalizer_result = None

    if normalizer_result:
        summary.pack_path = normalizer_result.pack_root.as_posix()
        summary.normalizer = {
            "manifest_path": normalizer_result.manifest_path.as_posix(),
            "thumbnails": normalizer_result.thumbnails,
            "sidecars": normalizer_result.sidecars,
        }
        summary.warnings.extend(normalizer_result.warnings)
        merged_manifest = dict(normalizer_result.manifest)
        if original_manifest:
            merged_manifest.setdefault("original_manifest", original_manifest)
            for key in ("id", "title", "licenses"):
                if key in original_manifest and key not in merged_manifest:
                    merged_manifest[key] = original_manifest[key]
        summary.manifest = merged_manifest
        if isinstance(merged_manifest.get("licenses"), list):
            summary.licenses = list(merged_manifest["licenses"])
    else:
        adapter_id = adapter_id or _infer_adapter(summary.manifest, seen_member_names)

    summary.adapter = adapter_id or "generic"
    if summary.manifest is None:
        summary.manifest = {"engine": summary.adapter}

    try:
        scene_paths = [scenes_dir / f"{scene}.json" for scene in summary.scenes]
        summary.translation = build_translation_bundle(scene_paths, import_root)
    except Exception as exc:
        summary.warnings.append(f"translation bundle failed: {exc}")
        logger.warning("Translation bundle failed for %s: %s", import_id, exc)

    try:
        manifest_for_remix = summary.manifest or {}
        summary.remix = plan_remix_tasks(manifest_for_remix, summary.scenes, import_root)
    except Exception as exc:
        summary.warnings.append(f"remix planning failed: {exc}")
        logger.warning("Remix planning failed for %s: %s", import_id, exc)

    summary_path = import_root / "summary.json"
    summary.summary_path = summary_path.as_posix()
    _write_json(summary_path, summary.to_dict())
    logger.info(
        "VN import '%s' complete (%d scenes, %d characters, %d assets)",
        summary.import_id,
        len(summary.scenes),
        len(summary.characters),
        len(summary.assets),
    )

    try:  # pragma: no cover - optional integration
        from comfyvn.server.core import indexer

        indexer.reindex()
    except Exception as exc:
        summary.warnings.append(f"reindex failed: {exc}")
        logger.warning("Reindex after import failed: %s", exc)

    return summary.to_dict()


__all__ = ["import_vn_package", "VNImportError", "ImportSummary"]
