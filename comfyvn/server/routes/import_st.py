"""FastAPI routes for SillyTavern chat imports."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from comfyvn.assets.persona_manager import PersonaManager
from comfyvn.config import feature_flags
from comfyvn.core.scene_store import SceneStore
from comfyvn.importers.st_chat import map_to_scenes, parse_st_file, parse_st_payload

try:  # Optional import guard for CLI contexts
    from comfyvn.core import modder_hooks  # type: ignore
    from comfyvn.core.modder_hooks import HookSpec  # type: ignore
except Exception:  # pragma: no cover - defensive
    modder_hooks = None  # type: ignore
    HookSpec = None  # type: ignore

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import/st", tags=["ST Importer"])

FEATURE_FLAG = "enable_st_importer"
IMPORT_ROOT = Path("imports")
TURN_FILE = "turns.json"
SCENES_FILE = "scenes.json"
STATUS_FILE = "status.json"
PREVIEW_FILE = "preview.json"

_SCENE_STORE = SceneStore()
_PERSONA_MANAGER = PersonaManager()

IMPORT_ROOT.mkdir(parents=True, exist_ok=True)


def _ensure_hook(name: str, spec: HookSpec) -> None:
    if modder_hooks is None:
        return
    registry = modder_hooks.HOOK_SPECS
    if name not in registry:
        registry[name] = spec


def _register_hooks() -> None:
    if modder_hooks is None or HookSpec is None:
        return
    _ensure_hook(
        "on_st_import_started",
        HookSpec(
            name="on_st_import_started",
            description="Emitted when an ST chat import run is initialised.",
            payload_fields={
                "run_id": "Import run identifier.",
                "project_id": "Target project identifier.",
                "source": "Input source descriptor (file/text/url).",
                "timestamp": "Unix epoch timestamp when the import queued.",
            },
            ws_topic="import.st.started",
            rest_event="on_st_import_started",
        ),
    )
    _ensure_hook(
        "on_st_import_scene_ready",
        HookSpec(
            name="on_st_import_scene_ready",
            description="Published for each scene produced by the ST importer.",
            payload_fields={
                "run_id": "Import run identifier.",
                "project_id": "Target project identifier.",
                "scene_id": "Generated scenario identifier.",
                "title": "Scene title.",
                "participants": "Detected participants for the scene.",
                "warnings": "Warnings recorded while mapping the scene.",
            },
            ws_topic="import.st.scene_ready",
            rest_event="on_st_import_scene_ready",
        ),
    )
    _ensure_hook(
        "on_st_import_completed",
        HookSpec(
            name="on_st_import_completed",
            description="Emitted when an ST import run finishes (successfully or failed).",
            payload_fields={
                "run_id": "Import run identifier.",
                "project_id": "Target project identifier.",
                "scene_count": "Number of scenes generated.",
                "warnings": "Aggregate warnings for the run.",
                "status": "Terminal status for the run: completed|failed.",
                "preview_path": "Path to the preview payload stored on disk.",
            },
            ws_topic="import.st.completed",
            rest_event="on_st_import_completed",
        ),
    )
    _ensure_hook(
        "on_st_import_failed",
        HookSpec(
            name="on_st_import_failed",
            description="Emitted when the ST importer encounters a fatal error.",
            payload_fields={
                "run_id": "Import run identifier.",
                "project_id": "Target project identifier.",
                "error": "Error message summarising the failure.",
                "timestamp": "Unix epoch timestamp when the error was recorded.",
            },
            ws_topic="import.st.failed",
            rest_event="on_st_import_failed",
        ),
    )


_register_hooks()


def _emit_hook(event: str, payload: Dict[str, Any]) -> None:
    if modder_hooks is None:
        return
    try:
        modder_hooks.emit(event, payload)
    except Exception:  # pragma: no cover - defensive
        LOGGER.debug("Modder hook '%s' emission failed", event, exc_info=True)


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    out = []
    for char in text:
        if char.isalnum():
            out.append(char)
        elif char in {" ", "-", "_"}:
            out.append("-")
    slug = "".join(out).strip("-")
    return slug or "item"


def _collect_persona_aliases() -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    try:
        personas = _PERSONA_MANAGER.list_personas()
    except Exception:
        LOGGER.debug("PersonaManager.list_personas() failed", exc_info=True)
        personas = []
    for entry in personas:
        persona_id = entry.get("id") or entry.get("persona_id")
        if not persona_id:
            continue
        names = {
            persona_id,
            entry.get("name"),
            entry.get("display_name"),
            entry.get("short_name"),
        }
        for name in names:
            if not name:
                continue
            normalized = _slugify(name)
            aliases.setdefault(normalized, persona_id)
            aliases.setdefault(str(name).strip().lower(), persona_id)
    return aliases


def _run_dir(run_id: str) -> Path:
    path = IMPORT_ROOT / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.debug("Failed to read JSON from %s", path, exc_info=True)
        return {}


def _update_status(
    run_dir: Path,
    *,
    phase: str,
    progress: float,
    project_id: str,
    **extra: Any,
) -> Dict[str, Any]:
    status_path = run_dir / STATUS_FILE
    current = _read_json(status_path)
    current.update(extra)
    current["phase"] = phase
    current["progress"] = max(0.0, min(1.0, float(progress)))
    current.setdefault("project_id", project_id)
    current["updated"] = time.time()
    _write_json(status_path, current)
    return current


def _aggregate_warnings(scenes: Sequence[Mapping[str, Any]]) -> List[str]:
    warnings: List[str] = []
    for scene in scenes:
        meta = scene.get("meta") or {}
        for item in meta.get("warnings", []) or []:
            if item not in warnings:
                warnings.append(item)
        for item in meta.get("unresolved_personas", []) or []:
            warning = f"Unresolved persona: {item}"
            if warning not in warnings:
                warnings.append(warning)
    return warnings


def _build_preview(
    project_id: str,
    run_id: str,
    turns: Sequence[Mapping[str, Any]],
    scenes: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    participants = set()
    for scene in scenes:
        meta = scene.get("meta") or {}
        for participant in meta.get("participants") or []:
            participants.add(str(participant))
    return {
        "run_id": run_id,
        "project_id": project_id,
        "scene_count": len(scenes),
        "turn_count": len(list(turns)),
        "participants": sorted(participants, key=lambda s: s.lower()),
        "generated_at": time.time(),
    }


def _persist_project_payload(
    project_id: str,
    scenes: Sequence[Mapping[str, Any]],
    run_id: str,
    preview_path: Path,
) -> None:
    project_root = Path("./data/projects")
    project_root.mkdir(parents=True, exist_ok=True)
    project_path = project_root / f"{project_id}.json"
    if project_path.exists():
        try:
            project_payload = json.loads(
                project_path.read_text(encoding="utf-8", errors="replace")
            )
        except Exception:
            project_payload = {"name": project_id}
    else:
        project_payload = {"name": project_id}
    project_payload.setdefault("name", project_id)
    scene_ids = project_payload.setdefault("scenes", [])
    for scene in scenes:
        scene_id = scene.get("id")
        if not scene_id:
            continue
        if scene_id not in scene_ids:
            scene_ids.append(scene_id)

    imports_meta = project_payload.setdefault("imports", {})
    st_history = imports_meta.setdefault("st_chat", [])
    st_history.append(
        {
            "run_id": run_id,
            "scene_ids": [scene.get("id") for scene in scenes if scene.get("id")],
            "preview": preview_path.as_posix(),
            "timestamp": time.time(),
        }
    )
    _write_json(project_path, project_payload)


def _save_scenes(scenes: Sequence[Mapping[str, Any]]) -> None:
    for scene in scenes:
        scene_id = scene.get("id")
        if not scene_id:
            continue
        _SCENE_STORE.save(scene_id, scene)


def _feature_enabled() -> bool:
    return feature_flags.is_enabled(FEATURE_FLAG, default=False)


def _require_feature_enabled() -> None:
    if not _feature_enabled():
        raise HTTPException(
            status_code=403,
            detail=f"Feature flag '{FEATURE_FLAG}' disabled.",
        )


async def _load_from_url(url: str) -> bytes:
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Only HTTP(S) URLs are supported.")
    timeout = httpx.Timeout(15.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch URL (status {response.status_code})",
            )
        return response.content


def _describe_source(
    *, file: UploadFile | None, text: Optional[str], url: Optional[str]
) -> str:
    if file and file.filename:
        return f"file:{file.filename}"
    if url:
        return f"url:{url}"
    if text:
        snippet = text.strip().splitlines()[0] if text.strip() else ""
        return f"text:{snippet[:40]}"
    return "unknown"


@router.post("/start")
async def st_import_start(
    projectId: str = Form(..., alias="projectId"),
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    url: str | None = Form(default=None),
) -> Dict[str, Any]:
    _require_feature_enabled()
    project_id = projectId.strip()
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required")

    if not file and not text and not url:
        raise HTTPException(
            status_code=400, detail="Provide one of file, text, or url inputs."
        )

    run_id = str(uuid.uuid4())
    run_dir = _run_dir(run_id)
    source_descriptor = _describe_source(file=file, text=text, url=url)

    LOGGER.info(
        "Starting ST chat import run %s (project=%s, source=%s)",
        run_id,
        project_id,
        source_descriptor,
    )
    _emit_hook(
        "on_st_import_started",
        {
            "run_id": run_id,
            "project_id": project_id,
            "source": source_descriptor,
            "timestamp": time.time(),
        },
    )

    status = _update_status(
        run_dir,
        phase="initializing",
        progress=0.05,
        project_id=project_id,
        run_id=run_id,
        source=source_descriptor,
    )
    try:
        tmp_path: Optional[Path] = None
        if file:
            data = await file.read()
            if not data:
                raise HTTPException(status_code=400, detail="Uploaded file is empty.")
            tmp_path = run_dir / (file.filename or "upload.bin")
            tmp_path.write_bytes(data)
            turns = parse_st_file(tmp_path)
        elif url:
            remote_bytes = await _load_from_url(url)
            tmp_path = run_dir / "remote_payload"
            tmp_path.write_bytes(remote_bytes)
            text_payload = remote_bytes.decode("utf-8", errors="replace")
            turns = parse_st_payload(text_payload)
        else:
            text_payload = text or ""
            tmp_path = run_dir / "inline.txt"
            tmp_path.write_text(text_payload, encoding="utf-8")
            turns = parse_st_payload(text_payload)

        status = _update_status(
            run_dir,
            phase="parsed",
            progress=0.4,
            project_id=project_id,
            turns=len(turns),
        )
        if not turns:
            raise HTTPException(
                status_code=422, detail="No chat turns detected in the supplied input."
            )

        persona_aliases = _collect_persona_aliases()
        scenes = map_to_scenes(
            project_id,
            turns,
            persona_aliases=persona_aliases,
            default_player_persona=(
                _PERSONA_MANAGER.state.get("active_persona")
                if hasattr(_PERSONA_MANAGER, "state")
                else None
            ),
        )
        if not scenes:
            raise HTTPException(
                status_code=422,
                detail="No scenes could be generated from the supplied SillyTavern transcript.",
            )
        status = _update_status(
            run_dir,
            phase="mapped",
            progress=0.7,
            project_id=project_id,
            scenes=[scene.get("id") for scene in scenes if scene.get("id")],
        )

        # Persist artifacts
        _write_json(run_dir / TURN_FILE, {"turns": turns})
        _write_json(run_dir / SCENES_FILE, {"scenes": scenes})

        _save_scenes(scenes)
        preview_payload = _build_preview(project_id, run_id, turns, scenes)
        preview_path = run_dir / PREVIEW_FILE
        _write_json(preview_path, preview_payload)
        _persist_project_payload(project_id, scenes, run_id, preview_path)

        warnings = _aggregate_warnings(scenes)
        status = _update_status(
            run_dir,
            phase="completed",
            progress=1.0,
            project_id=project_id,
            completed_at=time.time(),
            warnings=warnings,
            preview=preview_path.as_posix(),
        )

        for scene in scenes:
            scene_id = scene.get("id")
            meta = scene.get("meta") or {}
            _emit_hook(
                "on_st_import_scene_ready",
                {
                    "run_id": run_id,
                    "project_id": project_id,
                    "scene_id": scene_id,
                    "title": scene.get("title"),
                    "participants": meta.get("participants"),
                    "warnings": meta.get("warnings"),
                },
            )

        _emit_hook(
            "on_st_import_completed",
            {
                "run_id": run_id,
                "project_id": project_id,
                "scene_count": len(scenes),
                "warnings": warnings,
                "status": "completed",
                "preview_path": preview_path.as_posix(),
            },
        )

        return {
            "ok": True,
            "runId": run_id,
            "sceneCount": len(scenes),
            "warnings": warnings,
            "status": status,
        }
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("ST import run %s failed: %s", run_id, exc)
        _update_status(
            run_dir,
            phase="failed",
            progress=status.get("progress", 0.1) if isinstance(status, dict) else 0.1,
            project_id=project_id,
            error=str(exc),
        )
        _emit_hook(
            "on_st_import_failed",
            {
                "run_id": run_id,
                "project_id": project_id,
                "error": str(exc),
                "timestamp": time.time(),
            },
        )
        raise HTTPException(status_code=500, detail="ST import failed.") from exc


@router.get("/status/{run_id}")
async def st_import_status(run_id: str) -> Dict[str, Any]:
    run_dir = IMPORT_ROOT / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Import run not found.")
    status = _read_json(run_dir / STATUS_FILE)
    preview = _read_json(run_dir / PREVIEW_FILE)
    scenes_payload = _read_json(run_dir / SCENES_FILE)
    return {
        "ok": True,
        "runId": run_id,
        "phase": status.get("phase", "unknown"),
        "progress": status.get("progress", 0.0),
        "projectId": status.get("project_id"),
        "scenes": scenes_payload.get("scenes") or [],
        "warnings": status.get("warnings") or [],
        "updated": status.get("updated"),
        "preview": preview,
    }


__all__ = ["router"]
