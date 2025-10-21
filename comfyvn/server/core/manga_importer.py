from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from comfyvn.core.file_importer import FileImporter, ImportSession, log_license_issues
from comfyvn.server.core.translation_pipeline import build_translation_bundle

LOGGER = logging.getLogger(__name__)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class MangaImportError(RuntimeError):
    """Raised when a manga archive cannot be processed."""


@dataclass
class MangaImportSummary:
    import_id: str
    archive_path: str
    data_root: str
    title: str
    scenes: List[str] = field(default_factory=list)
    characters: List[str] = field(default_factory=list)
    timelines: List[str] = field(default_factory=list)
    assets: List[str] = field(default_factory=list)
    licenses: List[Dict[str, Any]] = field(default_factory=list)
    panels: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    translation: Dict[str, Any] = field(default_factory=dict)
    advisories: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    summary_path: Optional[str] = None
    raw_path: Optional[str] = None
    extracted_path: Optional[str] = None
    converted_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "import_id": self.import_id,
            "archive_path": self.archive_path,
            "data_root": self.data_root,
            "title": self.title,
            "scenes": self.scenes,
            "characters": self.characters,
            "timelines": self.timelines,
            "assets": self.assets,
            "licenses": self.licenses,
            "panels": self.panels,
            "warnings": self.warnings,
            "translation": self.translation,
            "advisories": self.advisories,
            "metadata": self.metadata,
            "summary_path": self.summary_path,
            "raw_path": self.raw_path,
            "extracted_path": self.extracted_path,
            "converted_path": self.converted_path,
        }


def import_manga_archive(
    archive_path: str | Path,
    *,
    data_root: Optional[Path] = None,
    project_id: Optional[str] = None,
    translation_enabled: bool = True,
    translation_lang: str = "en",
    license_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert a manga archive (CBZ/ZIP/folder) into draft VN scenes and timeline."""

    source = Path(archive_path).expanduser().resolve()
    if not source.exists():
        raise MangaImportError(f"archive not found: {source}")

    root = _resolve_data_root(data_root)
    import_id = f"{source.stem}-{int(time.time())}"
    file_importer = FileImporter("manga", data_root=root)
    session = file_importer.new_session(source, import_id=import_id)

    title = source.stem.replace("_", " ").strip() or "Imported Manga"
    summary = MangaImportSummary(
        import_id=import_id,
        archive_path=str(source),
        data_root=str(root),
        title=title,
    )
    summary.raw_path = session.raw_path.as_posix()
    summary.extracted_path = session.extracted_dir.as_posix()
    summary.converted_path = session.converted_dir.as_posix()

    LOGGER.info("Starting manga import '%s' from %s", import_id, source)

    stage_paths = _extract_archive(source, session)
    if not stage_paths:
        raise MangaImportError("no images found in archive")

    assets_root = root / "assets"
    manga_asset_root = assets_root / "manga" / import_id
    manga_asset_root.mkdir(parents=True, exist_ok=True)

    scenes_dir = root / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    characters_dir = root / "characters"
    characters_dir.mkdir(parents=True, exist_ok=True)
    timelines_dir = root / "timelines"
    timelines_dir.mkdir(parents=True, exist_ok=True)

    speakers: Dict[str, Dict[str, Any]] = {}
    timeline_entries: List[Dict[str, Any]] = []
    panels_metadata: List[Dict[str, Any]] = []

    for idx, image_path in enumerate(stage_paths, start=1):
        rel_key = image_path.relative_to(session.extracted_dir)
        asset_dest = manga_asset_root / rel_key
        asset_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, asset_dest)

        asset_rel = asset_dest.relative_to(assets_root).as_posix()
        summary.assets.append(asset_rel)

        panel_id = f"{import_id}-panel-{idx:03d}"
        scene_id = f"{import_id}_scene_{idx:03d}"
        transcripts = _load_transcript_candidates(image_path)
        if not transcripts:
            transcripts = [f"[Auto-OCR placeholder for {image_path.name}]"]

        scene_lines, detected_speakers = _build_scene_lines(transcripts, panel_id)
        for speaker in detected_speakers:
            speakers.setdefault(
                speaker,
                {"name": speaker, "character_id": _slugify(speaker), "source": "manga_import"},
            )

        scene_payload = {
            "scene_id": scene_id,
            "title": f"{title} · Page {idx}",
            "lines": scene_lines,
            "meta": {
                "import_id": import_id,
                "source_asset": asset_rel,
                "panel_count": 1,
                "import_kind": "manga",
                "project_id": project_id,
            },
            "panels": [
                {
                    "panel_id": panel_id,
                    "image": asset_rel,
                    "bbox": [0.0, 0.0, 1.0, 1.0],
                    "notes": "Full-page placeholder panel.",
                }
            ],
        }
        _write_json(scenes_dir / f"{scene_id}.json", scene_payload)
        summary.scenes.append(scene_id)

        timeline_entries.append(
            {
                "scene_id": scene_id,
                "title": scene_payload["title"],
                "notes": f"Draft panel for page {idx}",
                "meta": {"asset": asset_rel},
            }
        )

        panels_metadata.append(
            {
                "scene_id": scene_id,
                "panel_id": panel_id,
                "asset": asset_rel,
                "lines": scene_lines,
                "transcript_source": image_path.name,
            }
        )

    for speaker, char in speakers.items():
        char_id = char["character_id"]
        char_path = characters_dir / f"{char_id}.json"
        if not char_path.exists():
            payload = {
                "character_id": char_id,
                "name": speaker,
                "meta": {"import_id": import_id, "source": "manga_import"},
            }
            _write_json(char_path, payload)
        summary.characters.append(char_id)

    if timeline_entries:
        timeline_id = f"{import_id}_timeline"
        timeline_payload = {
            "timeline_id": timeline_id,
            "title": f"{title} Draft Timeline",
            "scene_order": timeline_entries,
            "meta": {"import_id": import_id, "source": "manga_import", "project_id": project_id},
        }
        _write_json(timelines_dir / f"{timeline_id}.json", timeline_payload)
        summary.timelines.append(timeline_id)

    pipeline_manifest = {
        "panels": len(panels_metadata),
        "ocr": {
            "lines_total": sum(len(panel["lines"]) for panel in panels_metadata),
            "handler": "stub",
            "language": translation_lang,
        },
        "speaker_heursitic": "colon-prefix",
    }
    summary.metadata["pipeline"] = pipeline_manifest
    summary.panels = panels_metadata

    panels_path = session.converted_dir / "panels.json"
    panels_path.write_text(json.dumps(panels_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    summary.metadata["panels_path"] = panels_path.as_posix()

    if license_hint:
        summary.licenses.append({"name": license_hint, "scope": "manga_assets", "source": "request"})

    if translation_enabled:
        try:
            scene_paths = [scenes_dir / f"{scene_id}.json" for scene_id in summary.scenes]
            summary.translation = build_translation_bundle(scene_paths, session.converted_dir, target_lang=translation_lang)
        except Exception as exc:  # pragma: no cover - defensive
            summary.warnings.append(f"translation bundle failed: {exc}")
            LOGGER.warning("Translation bundle failed for manga import %s: %s", import_id, exc)

    summary.advisories = log_license_issues(
        summary.import_id,
        summary.assets,
        summary.licenses,
        import_kind="manga",
    )

    summary_path = session.summary_path
    summary.summary_path = summary_path.as_posix()
    _write_json(summary_path, summary.to_dict())

    LOGGER.info(
        "Manga import '%s' complete (scenes=%d, characters=%d, assets=%d)",
        summary.import_id,
        len(summary.scenes),
        len(summary.characters),
        len(summary.assets),
    )

    return summary.to_dict()


def _resolve_data_root(explicit: Optional[Path] = None) -> Path:
    if explicit is not None:
        root = Path(explicit).expanduser().resolve()
    else:
        env = os.getenv("COMFYVN_DATA_ROOT")
        root = Path(env).expanduser() if env else Path("./data")
        root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _extract_archive(source: Path, session: ImportSession) -> List[Path]:
    stage_root = session.extracted_dir
    stage_root.mkdir(parents=True, exist_ok=True)
    extracted: List[Path] = []

    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source, "r") as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                safe_rel = _sanitize_member(member.filename)
                if safe_rel is None:
                    LOGGER.debug("Skipping unsafe archive member: %s", member.filename)
                    continue
                target = stage_root / safe_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
                extracted.append(target)
    elif source.is_dir():
        for file_path in sorted(source.rglob("*")):
            if file_path.is_file():
                safe_rel = _sanitize_member(file_path.relative_to(source).as_posix())
                if safe_rel is None:
                    continue
                target = stage_root / safe_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target)
                extracted.append(target)
    else:
        raise MangaImportError(f"unsupported archive format: {source.suffix}")

    images = [path for path in extracted if path.suffix.lower() in IMAGE_EXTS]
    images.sort(key=lambda p: p.relative_to(stage_root).as_posix())
    return images


def _sanitize_member(path: str) -> Optional[Path]:
    raw = Path(path)
    parts = [part for part in raw.parts if part not in {"", ".", "./"}]
    if not parts or any(part == ".." for part in parts):
        return None
    return Path(*parts)


def _load_transcript_candidates(image_path: Path) -> List[str]:
    candidates: Sequence[Path] = [
        image_path.with_suffix(".txt"),
        image_path.with_suffix(image_path.suffix + ".txt"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
                return [line.strip() for line in lines if line.strip()]
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.debug("Failed to read transcript %s: %s", candidate, exc)
                continue
    return []


def _build_scene_lines(transcripts: List[str], panel_id: str) -> tuple[List[Dict[str, Any]], List[str]]:
    lines: List[Dict[str, Any]] = []
    speakers: List[str] = []
    for order, raw in enumerate(transcripts, start=1):
        speaker, text = _split_speaker_text(raw)
        if speaker and speaker not in speakers and speaker not in {"Narrator", "Unknown"}:
            speakers.append(speaker)
        payload = {
            "speaker": speaker,
            "text": text,
            "meta": {
                "panel_id": panel_id,
                "order": order,
                "source": "ocr_stub",
                "confidence": 0.45 if speaker == "Unknown" else 0.6,
            },
        }
        lines.append(payload)
    if not lines:
        lines.append(
            {
                "speaker": "Narrator",
                "text": "[No OCR transcription available]",
                "meta": {"panel_id": panel_id, "order": 1, "source": "ocr_stub", "confidence": 0.1},
            }
        )
    return lines, speakers


def _split_speaker_text(raw: str) -> tuple[str, str]:
    match = re.match(r"(?P<speaker>[A-Za-z][^:：]{0,40})[:：]\s*(?P<text>.+)", raw)
    if match:
        speaker = match.group("speaker").strip()
        text = match.group("text").strip()
        if not text:
            text = raw.strip()
        return speaker or "Unknown", text
    if raw.lower().startswith(("narrator", "narration")):
        return "Narrator", raw.split(":", 1)[-1].strip()
    return "Unknown", raw.strip()


def _write_json(dest: Path, payload: Dict[str, Any]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_")
    slug = slug or "character"
    return slug.lower()


__all__ = ["import_manga_archive", "MangaImportError", "MangaImportSummary"]
