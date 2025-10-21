from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from starlette.datastructures import UploadFile

from comfyvn.config.runtime_paths import data_dir, imports_log_dir
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
RAW_DIR = data_dir("imports", "roleplay")
ASSET_TYPE = "transcripts"

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
            text_content = "\n".join(
                f"{line.get('speaker', 'Narrator')}: {line.get('text', '')}"
                for line in payload.structured_lines
                if isinstance(line, dict)
            )

        if not text_content and not payload.structured_lines:
            raise HTTPException(status_code=400, detail="Transcript content is empty.")

        raw_path = RAW_DIR / f"roleplay_{job_id}.txt"
        raw_path.write_text(text_content, encoding="utf-8")

        import_meta = {
            "job_id": job_id,
            "title": payload.title,
            "world": payload.world,
            "source": payload.source,
            "filename": payload.original_filename,
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

        scene_payload = _formatter.to_scene(
            parsed_lines,
            title=payload.title,
            world=payload.world,
            source=payload.source,
            job_ref=job_id,
        )

        scene_meta = scene_payload.get("meta", {})
        scene_body = json.dumps(scene_payload, ensure_ascii=False, indent=2)
        scene_db_id = _scene_registry.upsert_scene(scene_payload["title"], scene_body, scene_meta)

        linked_characters = []
        for name in scene_payload.get("meta", {}).get("participants", []):
            character_meta = {
                "origin": "roleplay_import",
                "job_id": job_id,
                "world": payload.world,
            }
            char_id = _character_registry.upsert_character(name, meta=character_meta)
            _character_registry.append_scene_link(char_id, scene_db_id)
            linked_characters.append({"id": char_id, "name": name})

        asset_metadata = {
            "job_id": job_id,
            "import_id": import_id,
            "scene_id": scene_db_id,
            "source": payload.source,
            "world": payload.world,
            "original_filename": payload.original_filename,
            "extra": payload.metadata,
        }
        provenance_payload = {
            "source": payload.source or "roleplay_import",
            "inputs": {
                "job_id": job_id,
                "import_id": import_id,
                "world": payload.world,
                "participants": scene_payload.get("meta", {}).get("participants", []),
                "original_filename": payload.original_filename,
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

        _import_registry.mark_processed(
            import_id,
            meta={**import_meta, "scene_id": scene_db_id, "asset_uid": asset_info["uid"]},
        )

        output_payload = {
            "scene_id": scene_db_id,
            "scene_uid": scene_payload["id"],
            "import_id": import_id,
            "asset_uid": asset_info["uid"],
            "participants": linked_characters,
        }
        _job_registry.update_job(job_id, status="completed", output_payload=output_payload)

        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[ok] scene_id={scene_db_id} lines={len(parsed_lines)} participants={linked_characters}\n")

        return {
            "ok": True,
            "job_id": job_id,
            "scene": scene_payload,
            "scene_db_id": scene_db_id,
            "asset": asset_info,
            "import_id": import_id,
            "logs_path": str(log_path),
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

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded = form.get("file")
        if isinstance(uploaded, UploadFile):
            data = await uploaded.read()
            text_content = data.decode("utf-8", errors="replace")
            original_filename = uploaded.filename or "roleplay.txt"
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
    elif "application/json" in content_type:
        payload = await request.json()
        text_content = str(payload.get("text") or payload.get("transcript") or "")
        world = payload.get("world")
        title = payload.get("title")
        source = payload.get("source") or "api"
        metadata = payload.get("metadata") or {}
        original_filename = payload.get("filename")
        lines_value = payload.get("lines")
        if isinstance(lines_value, list):
            lines_payload = [line for line in lines_value if isinstance(line, dict)]
        if "blocking" in payload:
            blocking = _parse_blocking(payload.get("blocking"))
    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported content-type. Use multipart/form-data or application/json.",
        )

    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata must be an object/dict.")

    if not text_content and (not lines_payload):
        raise HTTPException(status_code=400, detail="text or lines must be provided.")

    job_payload = RoleplayJobPayload(
        text_content=text_content,
        title=title,
        world=world,
        source=source,
        metadata=_merge_metadata(metadata),
        structured_lines=lines_payload or None,
        original_filename=original_filename,
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
