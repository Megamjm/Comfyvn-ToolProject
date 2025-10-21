from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from starlette.datastructures import UploadFile

from comfyvn.config.runtime_paths import data_dir, imports_log_dir
from comfyvn.core import advisory as advisory_core
from comfyvn.core.advisory import AdvisoryIssue
from comfyvn.core.file_importer import (
    ImportDirectories,
    build_preview_payload,
    flatten_lines,
    sanitize_filename,
)
from comfyvn.lmstudio_client import get_base_url as lmstudio_get_base_url
from comfyvn.studio.core import (
    AssetRegistry,
    CharacterRegistry,
    ImportRegistry,
    JobRegistry,
    SceneRegistry,
)

from .formatter import RoleplayFormatter
from .parser import RoleplayParser

router = APIRouter(prefix="/roleplay", tags=["Roleplay"])

LOGGER = logging.getLogger(__name__)

LOG_DIR = imports_log_dir()
ROLEPLAY_DIRS = ImportDirectories.ensure("roleplay")
ROLEPLAY_ROOT = ROLEPLAY_DIRS.root
RAW_DIR = ROLEPLAY_DIRS.raw
PROCESSED_DIR = ROLEPLAY_DIRS.converted
PREVIEW_DIR = ROLEPLAY_DIRS.preview
STATUS_DIR = data_dir("roleplay", "metadata")
LEGACY_RAW_DIR = data_dir("imports", "roleplay")
LEGACY_PROCESSED_DIR = data_dir("roleplay", "processed")
LEGACY_FINAL_DIR = data_dir("roleplay", "final")

for _dir in (
    ROLEPLAY_ROOT,
    RAW_DIR,
    PROCESSED_DIR,
    PREVIEW_DIR,
    STATUS_DIR,
    LEGACY_RAW_DIR,
    LEGACY_PROCESSED_DIR,
    LEGACY_FINAL_DIR,
    LOG_DIR,
):
    _dir.mkdir(parents=True, exist_ok=True)

ASSET_TYPE = "transcripts"
ASSET_TYPE_PROCESSED = "transcripts_processed"
ASSET_TYPE_FINAL = "transcripts_final"
DETAIL_LEVELS = {"low", "medium", "high"}
DETAIL_LEVEL_PROMPTS = {
    "low": (
        "Refine the transcript for clarity while preserving the original tone. "
        "Clarify actions or settings only when the original text is ambiguous. "
        "Do not invent new plot points; keep lines closely aligned with the source."
    ),
    "medium": (
        "Adapt the transcript into a visual novel scene. Maintain speaker ordering, "
        "ensure each line includes enough context for sprite or expression choices, "
        "and smooth abrupt transitions without changing outcomes."
    ),
    "high": (
        "Expand the transcript into a richly described scene. Add sensory details, "
        "internal thoughts, and pacing beats based on context while keeping character "
        "voices consistent. Split or merge lines if it improves flow, but keep the "
        "overall events consistent with the original."
    ),
}

_parser = RoleplayParser()
_formatter = RoleplayFormatter()
_scene_registry = SceneRegistry()
_character_registry = CharacterRegistry()
_job_registry = JobRegistry()
_import_registry = ImportRegistry()
_asset_registry = AssetRegistry()


@dataclass
class RoleplayJobPayload:
    text_content: str
    title: Optional[str]
    world: Optional[str]
    source: Optional[str]
    metadata: Dict[str, Any]
    structured_lines: Optional[List[Dict[str, Any]]]
    original_filename: Optional[str]
    detail_level: str = "medium"


def _normalize_detail_level(value: Any) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in DETAIL_LEVELS:
            return lowered
    return "medium"


def _raw_file(job_id: int) -> Path:
    return RAW_DIR / f"roleplay_{job_id}.txt"


def _processed_file(scene_uid: str) -> Path:
    return PROCESSED_DIR / f"{scene_uid}.json"


def _preview_file(scene_uid: str) -> Path:
    return PREVIEW_DIR / f"{scene_uid}.json"


def _status_file(scene_uid: str) -> Path:
    return STATUS_DIR / f"{scene_uid}.json"


def _load_processed_scene(scene_uid: str) -> Dict[str, Any]:
    path = _processed_file(scene_uid)
    if not path.exists():
        legacy_path = LEGACY_PROCESSED_DIR / f"{scene_uid}.json"
        if legacy_path.exists():
            path = legacy_path
        else:
            raise HTTPException(status_code=404, detail="Processed scene not found.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Processed scene payload corrupt: {exc}") from exc


def _load_preview(scene_uid: str) -> Dict[str, Any]:
    path = _preview_file(scene_uid)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview payload not found.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Preview payload corrupt: {exc}") from exc


def _save_processed_scene(scene_uid: str, payload: Dict[str, Any]) -> None:
    processed_path = _processed_file(scene_uid)
    processed_json = json.dumps(payload, ensure_ascii=False, indent=2)
    processed_path.write_text(processed_json, encoding="utf-8")
    try:
        legacy_processed = LEGACY_PROCESSED_DIR / processed_path.name
        legacy_processed.write_text(processed_json, encoding="utf-8")
    except Exception:  # pragma: no cover - optional legacy mirror
        LOGGER.debug("Unable to mirror legacy processed transcript path", exc_info=True)


def _save_preview(scene_uid: str, payload: Dict[str, Any]) -> None:
    preview_path = _preview_file(scene_uid)
    preview_json = json.dumps(payload, ensure_ascii=False, indent=2)
    preview_path.write_text(preview_json, encoding="utf-8")


def _load_status(scene_uid: str) -> Dict[str, Any]:
    path = _status_file(scene_uid)
    if not path.exists():
        legacy_path = LEGACY_FINAL_DIR / f"{scene_uid}.json"
        if legacy_path.exists():
            path = legacy_path
        else:
            raise HTTPException(status_code=404, detail="Scene status not found.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Status payload corrupt: {exc}") from exc


def _save_status(scene_uid: str, payload: Dict[str, Any]) -> None:
    status_path = _status_file(scene_uid)
    status_json = json.dumps(payload, ensure_ascii=False, indent=2)
    status_path.write_text(status_json, encoding="utf-8")
    try:
        legacy_status = LEGACY_FINAL_DIR / status_path.name
        legacy_status.write_text(status_json, encoding="utf-8")
    except Exception:  # pragma: no cover - optional legacy mirror
        LOGGER.debug("Unable to mirror legacy status path", exc_info=True)


def _mark_final_status(scene_uid: str, status: str, *, result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = _load_status(scene_uid)
    payload["status"] = status
    payload["updated_at"] = dt.datetime.utcnow().isoformat() + "Z"
    if result is not None:
        payload["result"] = result
    _save_status(scene_uid, payload)
    return payload


def _format_excerpt(lines: List[Dict[str, Any]]) -> str:
    formatted = []
    for idx, line in enumerate(lines, start=1):
        speaker = str(line.get("speaker") or "Narrator").strip()
        text = str(line.get("text") or "").strip()
        formatted.append(f"{idx}. {speaker}: {text}")
    return "\n".join(formatted)


def _build_llm_prompt(
    *,
    detail_level: str,
    lines: List[Dict[str, Any]],
    character_meta: Optional[Dict[str, Any]] = None,
    instructions: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    header = DETAIL_LEVEL_PROMPTS.get(detail_level, DETAIL_LEVEL_PROMPTS["medium"])
    prompt_sections = [header]

    if context:
        context_bits = []
        title = context.get("title")
        world = context.get("world")
        if title:
            context_bits.append(f"Scene Title: {title}")
        if world:
            context_bits.append(f"World Tag: {world}")
        if context_bits:
            prompt_sections.append("Context:\n" + "\n".join(context_bits))

    if character_meta:
        character_lines = [f"{name}: {desc}" for name, desc in character_meta.items() if desc]
        if character_lines:
            prompt_sections.append("Character Notes:\n" + "\n".join(character_lines))

    if instructions:
        prompt_sections.append("Additional Instructions:\n" + instructions.strip())

    prompt_sections.append("Original Transcript:\n" + _format_excerpt(lines))
    prompt_sections.append(
        "Return the revised scene as plain text. Maintain speaker prefixes where possible."
    )
    return "\n\n".join(section for section in prompt_sections if section)


def _loads_json(value: Any) -> Any:
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _serialize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    response = {
        "id": job["id"],
        "type": job["type"],
        "status": job["status"],
        "submit_ts": job["submit_ts"],
        "done_ts": job["done_ts"],
        "owner": job["owner"],
        "input": _loads_json(job.get("input_json")),
        "output": _loads_json(job.get("output_json")),
        "logs_path": job.get("logs_path"),
    }

    output = response.get("output") or {}
    import_id = output.get("import_id")
    import_record = _import_registry.get_import(import_id) if import_id else None
    if import_record:
        response["import"] = import_record
    return response


def _merge_metadata(meta: Any) -> Dict[str, Any]:
    return meta if isinstance(meta, dict) else {}


def _parse_blocking(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered in {"true", "1", "yes", "on"}
    return False


def _execute_import_job(job_id: int, payload: RoleplayJobPayload, log_path: Path) -> Dict[str, Any]:
    """Execute the roleplay import synchronously and update registries."""
    _job_registry.update_job(job_id, status="running")
    import_id: Optional[int] = None
    raw_path: Optional[Path] = None

    text_content = payload.text_content

    try:
        if not text_content and payload.structured_lines:
            structured = [line for line in payload.structured_lines if isinstance(line, dict)]
            text_content = flatten_lines(structured)

        if not text_content and not payload.structured_lines:
            raise HTTPException(status_code=400, detail="Transcript content is empty.")

        raw_path = _raw_file(job_id)
        raw_path.write_text(text_content, encoding="utf-8")
        try:
            legacy_raw = LEGACY_RAW_DIR / raw_path.name
            legacy_raw.write_text(text_content, encoding="utf-8")
        except Exception:  # pragma: no cover - optional legacy mirror
            LOGGER.debug("Unable to mirror legacy raw transcript path", exc_info=True)

        import_meta = {
            "job_id": job_id,
            "title": payload.title,
            "world": payload.world,
            "source": payload.source,
            "filename": payload.original_filename,
            "detail_level": payload.detail_level,
        }
        import_id = _import_registry.record_import(
            path=str(raw_path),
            kind="roleplay",
            processed=False,
            meta=import_meta,
        )

        if payload.structured_lines:
            parsed_lines = _parser.parse_json(json.dumps({"lines": payload.structured_lines}))
        else:
            parsed_lines = _parser.parse_text(text_content)

        if not parsed_lines:
            raise HTTPException(status_code=400, detail="Parsed transcript has no lines.")

        scene_payload = _formatter.to_scene(
            parsed_lines,
            title=payload.title,
            world=payload.world,
            source=payload.source,
            job_ref=job_id,
        )
        scene_meta = scene_payload.setdefault("meta", {})
        scene_meta["llm_detail"] = payload.detail_level
        scene_meta["line_count"] = len(parsed_lines)
        scene_uid = scene_payload["id"]

        canonical_transcript = text_content or flatten_lines(parsed_lines)
        advisory_flags = advisory_core.scan_text(
            scene_uid,
            canonical_transcript,
            license_scan=bool(payload.metadata.get("license")),
        )

        extra_issues: List[Dict[str, Any]] = []
        if not payload.metadata.get("license"):
            issue = AdvisoryIssue(
                scene_uid,
                "policy",
                "License metadata missing; manual review required",
                "warn",
                detail={"field": "license"},
            )
            advisory_core.log_issue(issue)
            extra_issues.append(issue.to_dict())

        safety_value = str(
            payload.metadata.get("safety")
            or payload.metadata.get("content_rating")
            or ""
        ).strip().lower()
        if safety_value not in {"sfw", "nsfw", "mixed"}:
            issue = AdvisoryIssue(
                scene_uid,
                "nsfw",
                "Content rating unknown; mark SFW/NSFW before distribution",
                "warn",
                detail={"field": "safety"},
            )
            advisory_core.log_issue(issue)
            extra_issues.append(issue.to_dict())

        if extra_issues:
            advisory_flags.extend(extra_issues)

        scene_meta["advisory_flags"] = advisory_flags

        scene_body = json.dumps(scene_payload, ensure_ascii=False, indent=2)
        scene_db_id = _scene_registry.upsert_scene(scene_payload["title"], scene_body, scene_meta)

        linked_characters = []
        persona_map = scene_meta.get("persona_hints", {})
        for name in scene_meta.get("participants", []):
            character_meta = {
                "origin": "roleplay_import",
                "job_id": job_id,
                "world": payload.world,
                "scene_uid": scene_uid,
                "advisory_flags": advisory_flags,
            }
            hints = persona_map.get(name, [])
            if hints:
                character_meta["persona_hints"] = hints
            char_id = _character_registry.upsert_character(
                name,
                traits={"persona_hints": hints} if hints else None,
                meta=character_meta,
            )
            _character_registry.append_scene_link(char_id, scene_db_id)
            linked_characters.append({"id": char_id, "name": name, "persona_hints": hints})

        processed_path = _processed_file(scene_uid)
        preview_path = _preview_file(scene_uid)
        status_path = _status_file(scene_uid)

        processed_payload = {
            "scene_uid": scene_uid,
            "scene_db_id": scene_db_id,
            "detail_level": payload.detail_level,
            "context": {
                "title": scene_payload["title"],
                "world": payload.world,
                "source": payload.source,
                "job_id": job_id,
                "import_id": import_id,
                "original_filename": payload.original_filename,
            },
            "lines": parsed_lines,
            "scene": scene_payload,
            "metadata": payload.metadata,
            "advisory_flags": advisory_flags,
            "persona_hints": persona_map,
        }
        processed_payload["preview_path"] = str(preview_path)
        processed_payload["status_path"] = str(status_path)
        _save_processed_scene(scene_uid, processed_payload)

        preview_payload = build_preview_payload(
            scene_uid=scene_uid,
            title=scene_payload["title"],
            detail_level=payload.detail_level,
            lines=parsed_lines,
            participants=scene_meta.get("participants", []),
            persona_hints=persona_map,
            advisory_flags=advisory_flags,
            world=payload.world,
            source=payload.source,
        )
        _save_preview(scene_uid, preview_payload)

        status_payload = {
            "scene_uid": scene_uid,
            "scene_db_id": scene_db_id,
            "detail_level": payload.detail_level,
            "status": "processing",
            "updated_at": dt.datetime.utcnow().isoformat() + "Z",
            "result": None,
            "job_id": job_id,
            "import_id": import_id,
            "advisory_flags": advisory_flags,
        }
        _save_status(scene_uid, status_payload)

        asset_metadata = {
            "job_id": job_id,
            "import_id": import_id,
            "scene_id": scene_db_id,
            "source": payload.source,
            "world": payload.world,
            "original_filename": payload.original_filename,
            "extra": payload.metadata,
            "detail_level": payload.detail_level,
            "advisory_flags": advisory_flags,
        }
        provenance_payload = {
            "source": payload.source or "roleplay_import",
            "inputs": {
                "job_id": job_id,
                "import_id": import_id,
                "world": payload.world,
                "participants": scene_payload.get("meta", {}).get("participants", []),
                "original_filename": payload.original_filename,
                "detail_level": payload.detail_level,
            },
            "user_id": payload.metadata.get("submitted_by"),
        }
        asset_info = _asset_registry.register_file(
            raw_path,
            asset_type=ASSET_TYPE,
            dest_relative=Path(ASSET_TYPE) / raw_path.name,
            metadata=asset_metadata,
            copy=True,
            provenance=provenance_payload,
            license_tag=payload.metadata.get("license"),
        )

        processed_asset = _asset_registry.register_file(
            processed_path,
            asset_type=ASSET_TYPE_PROCESSED,
            dest_relative=Path(ASSET_TYPE_PROCESSED) / processed_path.name,
            metadata={**asset_metadata, "stage": "processed"},
            copy=True,
            provenance=provenance_payload,
            license_tag=payload.metadata.get("license"),
        )

        preview_asset = _asset_registry.register_file(
            preview_path,
            asset_type=ASSET_TYPE_FINAL,
            dest_relative=Path(ASSET_TYPE_FINAL) / preview_path.name,
            metadata={**asset_metadata, "stage": "preview"},
            copy=True,
            provenance=provenance_payload,
            license_tag=payload.metadata.get("license"),
        )
        final_asset = preview_asset

        _import_registry.mark_processed(
            import_id,
            meta={
                **import_meta,
                "scene_id": scene_db_id,
                "scene_uid": scene_uid,
                "asset_uid": asset_info["uid"],
                "processed_asset_uid": processed_asset["uid"],
                "final_asset_uid": final_asset["uid"],
                "paths": {
                    "raw": str(raw_path),
                    "processed": str(processed_path),
                    "converted": str(processed_path),
                    "preview": str(preview_path),
                    "status": str(status_path),
                },
                "advisory_flags": advisory_flags,
            },
        )

        result_payload = {
            "scene_id": scene_db_id,
            "scene_uid": scene_uid,
            "preview_path": str(preview_path),
            "participants": scene_meta.get("participants", []),
            "advisory_flags": advisory_flags,
        }
        final_status = _mark_final_status(scene_uid, "ready", result=result_payload)

        output_payload = {
            "scene_id": scene_db_id,
            "scene_uid": scene_uid,
            "import_id": import_id,
            "asset_uid": asset_info["uid"],
            "processed_asset_uid": processed_asset["uid"],
            "final_asset_uid": final_asset["uid"],
            "preview_asset_uid": preview_asset["uid"],
            "participants": linked_characters,
            "detail_level": payload.detail_level,
            "advisory_flags": advisory_flags,
            "paths": {
                "raw": str(raw_path),
                "processed": str(processed_path),
                "converted": str(processed_path),
                "final": str(status_path),
                "status": str(status_path),
                "preview": str(preview_path),
            },
            "status": final_status,
        }
        _job_registry.update_job(job_id, status="completed", output_payload=output_payload)

        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                "[ok] scene_id=%s lines=%s participants=%s advisory=%s\n"
                % (
                    scene_db_id,
                    len(parsed_lines),
                    [entry["name"] for entry in linked_characters],
                    len(advisory_flags),
                )
            )

        return {
            "ok": True,
            "job_id": job_id,
            "scene": scene_payload,
            "scene_db_id": scene_db_id,
            "scene_uid": scene_uid,
            "asset": asset_info,
            "processed_asset": processed_asset,
            "final_asset": final_asset,
            "preview_asset": preview_asset,
            "detail_level": payload.detail_level,
            "advisory_flags": advisory_flags,
            "processed_path": str(processed_path),
            "converted_path": str(processed_path),
            "preview_path": str(preview_path),
            "status_path": str(status_path),
            "import_id": import_id,
            "logs_path": str(log_path),
            "preview": preview_payload,
            "status": final_status,
        }

    except HTTPException as exc:
        error_payload = {"error": exc.detail if isinstance(exc.detail, str) else "invalid payload"}
        _job_registry.update_job(job_id, status="failed", output_payload=error_payload)
        if import_id is not None:
            _import_registry.update_meta(
                import_id,
                meta={
                    "job_id": job_id,
                    "error": error_payload["error"],
                    "title": payload.title,
                    "world": payload.world,
                },
            )
        if raw_path and raw_path.exists():
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[error] {error_payload['error']}\n")
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.exception("Roleplay import failed: job_id=%s", job_id)
        _job_registry.update_job(job_id, status="failed", output_payload={"error": str(exc)})
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[error] {exc}\n")
        if import_id is not None:
            _import_registry.update_meta(
                import_id,
                meta={
                    "job_id": job_id,
                    "error": str(exc),
                    "title": payload.title,
                    "world": payload.world,
                },
            )
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}") from exc


def _run_job_background(job_id: int, payload: RoleplayJobPayload, log_path: Path) -> None:
    try:
        _execute_import_job(job_id, payload, log_path)
    except HTTPException as exc:
        LOGGER.warning("Background roleplay import failed job_id=%s: %s", job_id, exc.detail)
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Background roleplay import crashed job_id=%s", job_id)


def _spawn_import_thread(job_id: int, payload: RoleplayJobPayload, log_path: Path) -> None:
    thread = threading.Thread(
        target=_run_job_background,
        args=(job_id, payload, log_path),
        name=f"RoleplayImport-{job_id}",
        daemon=True,
    )
    thread.start()


def _wait_for_log(log_path: Path, timeout: float = 0.5) -> None:
    """Give the background job a moment to emit log output."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if log_path.exists() and log_path.stat().st_size > 0:
                break
        except OSError:
            break
        time.sleep(0.02)


@router.post("/import")
async def import_roleplay(request: Request):
    """
    Ingest a roleplay transcript (text or JSON) and queue a Scene import job.

    Optional field ``blocking`` allows callers to wait for completion.
    """
    content_type = request.headers.get("content-type", "")
    payload: Dict[str, Any] = {}
    text_content = ""
    world = None
    title = None
    source = None
    metadata: Dict[str, Any] = {}
    original_filename = None
    lines_payload: List[Dict[str, Any]] = []
    blocking = False
    detail_level_value: Optional[str] = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded = form.get("file")
        if isinstance(uploaded, UploadFile):
            data = await uploaded.read()
            text_content = data.decode("utf-8", errors="replace")
            original_filename = sanitize_filename(uploaded.filename, "roleplay.txt")
        else:
            text_content = str(form.get("text") or "")
        world = form.get("world")
        title = form.get("title")
        source = form.get("source") or "upload"
        meta_field = form.get("metadata")
        if meta_field:
            try:
                metadata = json.loads(meta_field)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"metadata must be valid JSON: {exc}") from exc
        if "blocking" in form:
            blocking = _parse_blocking(form.get("blocking"))
        detail_level_value = form.get("detail_level")
    elif "application/json" in content_type:
        payload = await request.json()
        text_content = str(payload.get("text") or payload.get("transcript") or "")
        world = payload.get("world")
        title = payload.get("title")
        source = payload.get("source") or "api"
        metadata = payload.get("metadata") or {}
        if payload.get("filename"):
            original_filename = sanitize_filename(payload.get("filename"))
        lines_value = payload.get("lines")
        if isinstance(lines_value, list):
            lines_payload = [line for line in lines_value if isinstance(line, dict)]
        if "blocking" in payload:
            blocking = _parse_blocking(payload.get("blocking"))
        detail_level_value = payload.get("detail_level")
    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported content-type. Use multipart/form-data or application/json.",
        )

    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata must be an object/dict.")

    if not text_content and (not lines_payload):
        raise HTTPException(status_code=400, detail="text or lines must be provided.")

    detail_level = _normalize_detail_level(detail_level_value)
    metadata = {**metadata, "llm_detail": detail_level}
    if original_filename:
        metadata["original_filename"] = original_filename

    job_payload = RoleplayJobPayload(
        text_content=text_content,
        title=title,
        world=world,
        source=source,
        metadata=_merge_metadata(metadata),
        structured_lines=lines_payload or None,
        original_filename=original_filename,
        detail_level=detail_level,
    )

    job_id = _job_registry.create_job(
        "roleplay_import",
        status="queued",
        input_payload={
            "title": job_payload.title,
            "world": job_payload.world,
            "source": job_payload.source,
            "filename": job_payload.original_filename,
            "metadata_keys": sorted(job_payload.metadata.keys()),
            "has_lines": bool(job_payload.structured_lines),
            "detail_level": job_payload.detail_level,
        },
        owner="api",
    )

    log_path = LOG_DIR / f"roleplay_{job_id}.log"
    log_path.touch(exist_ok=True)
    _job_registry.update_job(job_id, logs_path=str(log_path))

    if blocking:
        return _execute_import_job(job_id, job_payload, log_path)

    _spawn_import_thread(job_id, job_payload, log_path)
    _wait_for_log(log_path)
    return {
        "ok": True,
        "job_id": job_id,
        "status": "queued",
        "logs_path": str(log_path),
    }


@router.get("/imports/{job_id}")
@router.get("/imports/status/{job_id}")
def import_status(job_id: int):
    """Return the job/import status for a previously submitted transcript."""
    job = _job_registry.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"ok": True, "job": _serialize_job(job)}


@router.get("/imports")
def list_imports(limit: int = Query(20, ge=1, le=100)):
    """List recent roleplay import jobs."""
    jobs = _job_registry.list_jobs("roleplay_import", limit)
    items = []
    for job in jobs:
        job_detail = _job_registry.get_job(job["id"])
        if job_detail:
            items.append(_serialize_job(job_detail))
    return {"ok": True, "items": items}


@router.get("/imports/{job_id}/log", response_class=PlainTextResponse)
def get_import_log(job_id: int):
    """Return the textual log output for a roleplay import job."""
    job = _job_registry.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    log_path = job.get("logs_path")
    if not log_path:
        raise HTTPException(status_code=404, detail="Log not recorded for this job.")

    path = Path(log_path).expanduser().resolve()
    try:
        path.relative_to(LOG_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Log path outside allowed directory.")

    if not path.exists():
        raise HTTPException(status_code=404, detail="Log file missing.")

    return path.read_text(encoding="utf-8")


@router.get("/preview/{scene_uid}")
def preview_scene(scene_uid: str):
    data = _load_processed_scene(scene_uid)
    preview_payload: Optional[Dict[str, Any]] = None
    try:
        preview_payload = _load_preview(scene_uid)
    except HTTPException:
        preview_payload = None

    status_payload: Optional[Dict[str, Any]] = None
    try:
        status_payload = _load_status(scene_uid)
    except HTTPException:
        status_payload = None
    return {
        "ok": True,
        "scene_uid": scene_uid,
        "detail_level": data.get("detail_level", "medium"),
        "lines": data.get("lines", []),
        "scene": data.get("scene"),
        "context": data.get("context", {}),
        "metadata": data.get("metadata", {}),
        "advisory_flags": data.get("advisory_flags", []),
        "preview": preview_payload,
        "status": status_payload,
        "final": status_payload,
    }


@router.post("/apply_corrections")
def apply_corrections(payload: Dict[str, Any]):
    scene_uid = str(payload.get("scene_id") or payload.get("scene_uid") or "").strip()
    if not scene_uid:
        raise HTTPException(status_code=400, detail="scene_id is required")

    processed = _load_processed_scene(scene_uid)
    context = processed.get("context") or {}
    detail_level = _normalize_detail_level(payload.get("detail_level") or processed.get("detail_level"))
    raw_lines = payload.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise HTTPException(status_code=400, detail="lines must be a non-empty list")

    sanitized_lines: List[Dict[str, Any]] = []
    for line in raw_lines:
        if not isinstance(line, dict):
            continue
        speaker = str(line.get("speaker") or "Narrator").strip()
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        sanitized_lines.append({"speaker": speaker, "text": text})

    if not sanitized_lines:
        raise HTTPException(status_code=400, detail="No valid lines provided")

    scene_payload = _formatter.to_scene(
        sanitized_lines,
        title=context.get("title"),
        world=context.get("world"),
        source=context.get("source"),
        job_ref=context.get("job_id"),
    )
    scene_meta = scene_payload.setdefault("meta", {})
    scene_meta["llm_detail"] = detail_level
    scene_meta["line_count"] = len(sanitized_lines)

    metadata_payload = processed.get("metadata") or {}
    canonical_transcript = flatten_lines(sanitized_lines)
    advisory_flags = advisory_core.scan_text(
        scene_uid,
        canonical_transcript,
        license_scan=bool(metadata_payload.get("license")),
    )

    extra_issues: List[Dict[str, Any]] = []
    if not metadata_payload.get("license"):
        issue = AdvisoryIssue(
            scene_uid,
            "policy",
            "License metadata missing; manual review required",
            "warn",
            detail={"field": "license"},
        )
        advisory_core.log_issue(issue)
        extra_issues.append(issue.to_dict())

    safety_value = str(
        metadata_payload.get("safety") or metadata_payload.get("content_rating") or ""
    ).strip().lower()
    if safety_value not in {"sfw", "nsfw", "mixed"}:
        issue = AdvisoryIssue(
            scene_uid,
            "nsfw",
            "Content rating unknown; mark SFW/NSFW before distribution",
            "warn",
            detail={"field": "safety"},
        )
        advisory_core.log_issue(issue)
        extra_issues.append(issue.to_dict())

    if extra_issues:
        advisory_flags.extend(extra_issues)

    scene_meta["advisory_flags"] = advisory_flags

    scene_body = json.dumps(scene_payload, ensure_ascii=False, indent=2)
    scene_db_id_context = processed.get("scene_db_id") or context.get("scene_db_id")
    if scene_db_id_context:
        scene_db_id = _scene_registry.upsert_scene(
            scene_payload["title"],
            scene_body,
            scene_meta,
            scene_id=int(scene_db_id_context),
        )
    else:
        scene_db_id = _scene_registry.upsert_scene(scene_payload["title"], scene_body, scene_meta)

    preview_path = _preview_file(scene_uid)
    status_path = _status_file(scene_uid)

    processed.update(
        {
            "scene": scene_payload,
            "lines": sanitized_lines,
            "detail_level": detail_level,
            "scene_db_id": scene_db_id,
            "character_meta": payload.get("character_meta") or processed.get("character_meta") or {},
            "advisory_flags": advisory_flags,
            "persona_hints": scene_meta.get("persona_hints", {}),
            "preview_path": str(preview_path),
            "status_path": str(status_path),
        }
    )
    _save_processed_scene(scene_uid, processed)

    preview_payload = build_preview_payload(
        scene_uid=scene_uid,
        title=scene_payload["title"],
        detail_level=detail_level,
        lines=sanitized_lines,
        participants=scene_meta.get("participants", []),
        persona_hints=scene_meta.get("persona_hints", {}),
        advisory_flags=advisory_flags,
        world=context.get("world"),
        source=context.get("source"),
    )
    _save_preview(scene_uid, preview_payload)

    asset_metadata = {
        "scene_id": scene_db_id,
        "scene_uid": scene_uid,
        "stage": "processed",
        "detail_level": detail_level,
        "advisory_flags": advisory_flags,
    }
    provenance_payload = {
        "source": context.get("source") or "roleplay_import",
        "inputs": {
            "scene_uid": scene_uid,
            "scene_id": scene_db_id,
            "job_id": context.get("job_id"),
            "detail_level": detail_level,
        },
    }
    processed_path = _processed_file(scene_uid)
    processed_asset = _asset_registry.register_file(
        processed_path,
        asset_type=ASSET_TYPE_PROCESSED,
        dest_relative=Path(ASSET_TYPE_PROCESSED) / processed_path.name,
        metadata=asset_metadata,
        copy=True,
        provenance=provenance_payload,
    )

    preview_asset = _asset_registry.register_file(
        preview_path,
        asset_type=ASSET_TYPE_FINAL,
        dest_relative=Path(ASSET_TYPE_FINAL) / preview_path.name,
        metadata={**asset_metadata, "stage": "preview"},
        copy=True,
        provenance=provenance_payload,
    )

    result_payload = {
        "scene_id": scene_db_id,
        "scene_uid": scene_uid,
        "preview_path": str(preview_path),
        "advisory_flags": advisory_flags,
    }
    final_payload: Dict[str, Any]
    try:
        final_payload = _mark_final_status(scene_uid, "stale", result=result_payload)
    except HTTPException:
        # Recreate status stub when missing.
        _save_status(
            scene_uid,
            {
                "scene_uid": scene_uid,
                "scene_db_id": scene_db_id,
                "detail_level": detail_level,
                "status": "stale",
                "updated_at": dt.datetime.utcnow().isoformat() + "Z",
                "result": result_payload,
                "advisory_flags": advisory_flags,
            },
        )
        final_payload = _mark_final_status(scene_uid, "stale", result=result_payload)

    return {
        "ok": True,
        "scene_uid": scene_uid,
        "scene": scene_payload,
        "scene_db_id": scene_db_id,
        "detail_level": detail_level,
        "processed_asset": processed_asset,
        "preview_asset": preview_asset,
        "final_asset": preview_asset,
        "advisory_flags": advisory_flags,
        "preview": preview_payload,
        "status": final_payload,
        "final": final_payload,
    }


@router.post("/sample_llm")
def sample_llm(payload: Dict[str, Any]):
    scene_uid = str(payload.get("scene_id") or payload.get("scene_uid") or "").strip()
    if not scene_uid:
        raise HTTPException(status_code=400, detail="scene_id is required")

    processed = _load_processed_scene(scene_uid)
    lines = payload.get("excerpt") or processed.get("lines") or []
    if not isinstance(lines, list) or not lines:
        raise HTTPException(status_code=400, detail="excerpt must include at least one line")

    character_meta = payload.get("character_meta") or processed.get("character_meta") or {}
    instructions = payload.get("instructions")
    detail_level = _normalize_detail_level(payload.get("detail_level") or processed.get("detail_level"))
    context = processed.get("context", {})

    prompt = _build_llm_prompt(
        detail_level=detail_level,
        lines=lines,
        character_meta=character_meta,
        instructions=instructions,
        context=context,
    )

    base_url = str(payload.get("endpoint") or lmstudio_get_base_url()).rstrip("/")
    model = payload.get("model") or "auto"
    api_key = payload.get("api_key")
    temperature = 0.25 if detail_level == "low" else (0.5 if detail_level == "medium" else 0.75)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request_payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a narrative editor helping refine visual novel transcripts.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "stream": False,
    }

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            json=request_payload,
            headers=headers,
            timeout=float(payload.get("timeout", 180)),
        )
        response.raise_for_status()
        data = response.json()
        text = ""
        if isinstance(data, dict):
            choices = data.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                text = message.get("content", "").strip()
    except Exception as exc:  # pragma: no cover - network dependent
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

    result_payload = {
        "text": text,
        "detail_level": detail_level,
        "model": model,
        "endpoint": base_url,
        "character_meta": character_meta,
        "instructions": instructions,
        "excerpt": lines,
    }

    final_payload = _mark_final_status(scene_uid, "ready", result=result_payload)
    status_path = _status_file(scene_uid)
    final_asset = _asset_registry.register_file(
        status_path,
        asset_type=ASSET_TYPE_FINAL,
        dest_relative=Path(ASSET_TYPE_FINAL) / status_path.name,
        metadata={
            "scene_uid": scene_uid,
            "stage": "status",
            "detail_level": detail_level,
            "model": model,
        },
        copy=True,
        provenance={
            "source": "roleplay_llm",
            "inputs": {"scene_uid": scene_uid, "model": model},
        },
    )

    return {
        "ok": True,
        "scene_uid": scene_uid,
        "detail_level": detail_level,
        "llm_output": text,
        "final": final_payload,
        "final_asset": final_asset,
    }
