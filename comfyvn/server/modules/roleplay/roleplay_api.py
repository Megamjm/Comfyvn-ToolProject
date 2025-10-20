from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from starlette.datastructures import UploadFile

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

LOG_DIR = Path("logs/imports")
RAW_DIR = Path("data/imports/roleplay")
ASSET_TYPE = "transcripts"

for directory in (LOG_DIR, RAW_DIR):
    directory.mkdir(parents=True, exist_ok=True)

_parser = RoleplayParser()
_formatter = RoleplayFormatter()
_scene_registry = SceneRegistry()
_character_registry = CharacterRegistry()
_job_registry = JobRegistry()
_import_registry = ImportRegistry()
_asset_registry = AssetRegistry()


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


@router.post("/import")
async def import_roleplay(request: Request):
    """
    Ingest a roleplay transcript (text or JSON) and generate a Scene record.

    Accepted payloads:
      * multipart/form-data with fields `file` (UploadFile) or `text`
      * application/json with `text`, `lines`, or `transcript`

    Optional fields: `title`, `world`, `source`, `metadata`.
    """
    content_type = request.headers.get("content-type", "")
    payload: Dict[str, Any] = {}
    text_content = ""
    world = None
    title = None
    source = None
    metadata: Dict[str, Any] = {}
    original_filename = None

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
    elif "application/json" in content_type:
        payload = await request.json()
        text_content = str(payload.get("text") or payload.get("transcript") or "")
        world = payload.get("world")
        title = payload.get("title")
        source = payload.get("source") or "api"
        metadata = payload.get("metadata") or {}
        original_filename = payload.get("filename")
    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported content-type. Use multipart/form-data or application/json.",
        )

    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata must be an object/dict.")

    job_input = {"title": title, "world": world, "source": source}
    job_id = _job_registry.create_job("roleplay_import", owner="roleplay.api", input_payload=job_input)
    log_path = LOG_DIR / f"roleplay_{job_id}.log"
    _job_registry.update_job(job_id, logs_path=str(log_path))

    import_id: int | None = None
    raw_path: Path | None = None

    try:
        if not text_content and payload.get("lines"):
            # Fallback: serialise structured lines to text for archival.
            text_content = "\n".join(
                f"{line.get('speaker', 'Narrator')}: {line.get('text', '')}"
                for line in payload["lines"]
                if isinstance(line, dict)
            )

        if not text_content and not payload.get("lines"):
            raise HTTPException(status_code=400, detail="Transcript content is empty.")

        raw_path = RAW_DIR / f"roleplay_{job_id}.txt"
        raw_path.write_text(text_content, encoding="utf-8")

        import_meta = {
            "job_id": job_id,
            "title": title,
            "world": world,
            "source": source,
            "filename": original_filename,
        }
        import_id = _import_registry.record_import(
            path=str(raw_path),
            kind="roleplay",
            processed=False,
            meta=import_meta,
        )

        # Parse transcript into structured lines.
        if payload.get("lines"):
            lines = _parser.parse_json(json.dumps({"lines": payload["lines"]}))
        else:
            lines = _parser.parse_text(text_content)

        scene_payload = _formatter.to_scene(
            lines,
            title=title,
            world=world,
            source=source,
            job_ref=job_id,
        )

        scene_meta = scene_payload.get("meta", {})
        scene_body = json.dumps(scene_payload, ensure_ascii=False, indent=2)
        scene_db_id = _scene_registry.upsert_scene(scene_payload["title"], scene_body, scene_meta)

        # Ensure characters exist and link scene.
        linked_characters = []
        for name in scene_payload["meta"].get("participants", []):
            character_meta = {
                "origin": "roleplay_import",
                "job_id": job_id,
                "world": world,
            }
            char_id = _character_registry.upsert_character(name, meta=character_meta)
            _character_registry.append_scene_link(char_id, scene_db_id)
            linked_characters.append({"id": char_id, "name": name})

        asset_metadata = {
            "job_id": job_id,
            "import_id": import_id,
            "scene_id": scene_db_id,
            "source": source,
            "world": world,
            "original_filename": original_filename,
            "extra": metadata,
        }
        provenance_payload = {
            "source": source or "roleplay_import",
            "inputs": {
                "job_id": job_id,
                "import_id": import_id,
                "world": world,
                "participants": scene_payload.get("meta", {}).get("participants", []),
                "original_filename": original_filename,
            },
            "user_id": metadata.get("submitted_by") if isinstance(metadata, dict) else None,
        }
        asset_info = _asset_registry.register_file(
            raw_path,
            asset_type=ASSET_TYPE,
            dest_relative=Path(ASSET_TYPE) / raw_path.name,
            metadata=asset_metadata,
            copy=True,
            provenance=provenance_payload,
            license_tag=metadata.get("license") if isinstance(metadata, dict) else None,
        )

        _import_registry.mark_processed(import_id, meta={**import_meta, "scene_id": scene_db_id, "asset_uid": asset_info["uid"]})

        output_payload = {
            "scene_id": scene_db_id,
            "scene_uid": scene_payload["id"],
            "import_id": import_id,
            "asset_uid": asset_info["uid"],
            "participants": linked_characters,
        }
        _job_registry.update_job(job_id, status="completed", output_payload=output_payload)

        # Append to human-readable log for quick triage.
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[ok] scene_id={scene_db_id} lines={len(lines)} participants={linked_characters}\n")

        return {
            "ok": True,
            "job_id": job_id,
            "scene": scene_payload,
            "scene_db_id": scene_db_id,
            "asset": asset_info,
            "import_id": import_id,
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
                    "title": title,
                    "world": world,
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
                    "title": title,
                    "world": world,
                },
            )
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}") from exc


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
