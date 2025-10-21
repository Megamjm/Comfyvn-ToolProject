from __future__ import annotations
import json
import logging
import threading
import uuid
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from PySide6.QtGui import QAction

from comfyvn.core.task_registry import task_registry
from comfyvn.server.core.chat_import import apply_alias_map, assign_by_patterns, parse_text, to_scene_dict
from comfyvn.server.core.manga_importer import MangaImportError, import_manga_archive
from comfyvn.server.modules.auth import require_scope

router = APIRouter()
logger = logging.getLogger("comfyvn.api.imports")

SCENE_DIR = Path("./data/scenes"); SCENE_DIR.mkdir(parents=True, exist_ok=True)

def _write_scene(name: str, data: Dict[str, Any]) -> str:
    p = (SCENE_DIR / f"{name}.json").resolve()
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return name


def _task_meta(task_id: str) -> Dict[str, Any]:
    task = task_registry.get(task_id)
    if task and task.meta:
        return dict(task.meta)
    return {}


def _serialize_task(task) -> Dict[str, Any]:
    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "meta": task.meta,
    }


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return bool(value)


def _load_summary_from_meta(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    summary = meta.get("result") if isinstance(meta, dict) else None
    if summary:
        return summary
    path = meta.get("summary_path") if isinstance(meta, dict) else None
    if path:
        try:
            file_path = Path(path)
            if file_path.exists():
                return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - defensive
            logger.debug("Failed to load summary at %s", path, exc_info=True)
    return None


def _data_root() -> Path:
    env = os.getenv("COMFYVN_DATA_ROOT")
    base = Path(env).expanduser() if env else Path("./data")
    return base.resolve()


def _load_manga_history(limit: int = 20) -> List[Dict[str, Any]]:
    base = _data_root() / "imports" / "manga"
    converted = base / "converted"
    summary_paths: List[Path] = []
    if converted.exists():
        summary_paths.extend(converted.glob("*/summary.json"))
    if base.exists():
        summary_paths.extend(base.glob("*/summary.json"))
    if not summary_paths:
        return []
    files = sorted(summary_paths, key=lambda p: p.stat().st_mtime, reverse=True)
    seen: set[Path] = set()
    history: List[Dict[str, Any]] = []
    for path in files:
        if len(history) >= limit:
            break
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("summary_path", path.as_posix())
            history.append(data)
        except Exception:  # pragma: no cover - defensive
            logger.debug("Skipping malformed summary %s", path, exc_info=True)
    return history


def _execute_manga_import(task_id: str, archive: str, options: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[Manga Import] job=%s starting -> %s", task_id, archive)
    task_registry.update(task_id, status="running", progress=0.05, message="Preparing manga import")
    try:
        summary = import_manga_archive(archive, **options)
    except MangaImportError as exc:
        meta = _task_meta(task_id)
        meta["error"] = str(exc)
        task_registry.update(task_id, status="error", progress=1.0, message=str(exc), meta=meta)
        logger.warning("[Manga Import] job=%s failed: %s", task_id, exc)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        meta = _task_meta(task_id)
        meta["error"] = str(exc)
        task_registry.update(task_id, status="error", progress=1.0, message="manga import failed", meta=meta)
        logger.exception("[Manga Import] job=%s failed unexpectedly", task_id)
        raise

    stats = (
        f"scenes={len(summary.get('scenes', []))} "
        f"assets={len(summary.get('assets', []))} "
        f"characters={len(summary.get('characters', []))}"
    )
    meta = _task_meta(task_id)
    meta["result"] = summary
    meta["summary_path"] = summary.get("summary_path")
    task_registry.update(
        task_id,
        status="done",
        progress=1.0,
        message=f"Manga import complete ({stats})",
        meta=meta,
    )
    logger.info("[Manga Import] job=%s complete %s", task_id, stats)
    return summary


def _spawn_manga_job(task_id: str, archive: str, options: Dict[str, Any]) -> None:
    def _runner() -> None:
        try:
            _execute_manga_import(task_id, archive, options)
        except MangaImportError:
            return
        except Exception:
            return

    threading.Thread(target=_runner, name=f"MangaImport-{task_id[:8]}", daemon=True).start()
@router.post("/chat")
async def import_chat(body: Dict[str, Any], _: bool = Depends(require_scope(["content.write"]))):
    text = str(body.get("text") or "")
    if not text.strip(): raise HTTPException(status_code=400, detail="text required")
    fmt = str(body.get("format") or "auto")
    base = str(body.get("name") or f"scene_{uuid.uuid4().hex[:8]}" )
    alias = body.get("alias_map") or {}
    rules = body.get("assign_rules") or []
    split_on = str(body.get("split_on") or "")  # regex boundary to split into scenes
    max_lines = int(body.get("max_lines") or 0)

    # initial parse
    lines = parse_text(text, fmt=fmt)
    lines = apply_alias_map(lines, alias)
    lines = assign_by_patterns(lines, rules)

    # split logic
    scenes: List[List[dict]] = []
    if split_on:
        import re as _re
        current: List[dict] = []
        rgx = _re.compile(split_on, _re.IGNORECASE)
        for ln in lines:
            if rgx.search(ln.text):
                if current: scenes.append(current); current = []
                continue
            current.append(ln)
        if current: scenes.append(current)
    elif max_lines and max_lines>0:
        current: List[dict] = []
        for ln in lines:
            current.append(ln)
            if len(current) >= max_lines:
                scenes.append(current); current = []
        if current: scenes.append(current)
    else:
        scenes = [lines]

    created = []
    for i, seq in enumerate(scenes):
        name = base if len(scenes)==1 else f"{base}_{i+1:02d}"
        data = to_scene_dict(name, seq)
        _write_scene(name, data)
        created.append(name)
    return {"ok": True, "created": created, "count": len(created)}


@router.post("/manga/import")
async def manga_import(payload: Dict[str, Any], _: bool = Depends(require_scope(["content.write"], cost=5))):
    path_value = payload.get("path") or payload.get("archive_path")
    if not path_value:
        raise HTTPException(status_code=400, detail="path is required")

    archive_path = Path(path_value).expanduser()
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="archive path not found")
    options: Dict[str, Any] = {}

    data_root_value = payload.get("data_root")
    if data_root_value:
        options["data_root"] = Path(data_root_value).expanduser()

    translation_enabled = _coerce_bool(payload.get("translation"), default=True)
    options["translation_enabled"] = translation_enabled
    options["translation_lang"] = str(payload.get("translation_lang") or "en")

    project_id = payload.get("project_id")
    if project_id:
        options["project_id"] = str(project_id)

    license_hint = payload.get("license") or payload.get("license_hint")
    if license_hint:
        options["license_hint"] = str(license_hint)

    blocking = _coerce_bool(payload.get("blocking"), default=False)

    task_id = task_registry.register(
        "manga.import",
        {"path": str(archive_path), "project_id": options.get("project_id")},
        message=f"Manga import {archive_path.name}",
        meta={"archive": str(archive_path), "project_id": options.get("project_id")},
    )

    if blocking:
        try:
            summary = _execute_manga_import(task_id, str(archive_path), options)
        except MangaImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=500, detail="manga import failed") from exc
        return {"ok": True, "import": summary, "job": {"id": task_id}}

    try:
        _spawn_manga_job(task_id, str(archive_path), options)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to spawn manga import job: %s", exc)
        raise HTTPException(status_code=500, detail="manga import spawn failed") from exc

    return {"ok": True, "job": {"id": task_id}}


@router.get("/manga/import/{job_id}")
async def manga_import_status(job_id: str, _: bool = Depends(require_scope(["content.read"], cost=1))):
    task = task_registry.get(job_id)
    if not task:
        raise HTTPException(status_code=404, detail="job not found")
    summary = _load_summary_from_meta(task.meta or {})
    return {"ok": True, "job": _serialize_task(task), "summary": summary}


@router.get("/manga/imports/history")
async def manga_import_history(limit: int = 20, _: bool = Depends(require_scope(["content.read"], cost=1))):
    limit = max(1, min(int(limit), 200))
    history = _load_manga_history(limit)
    return {"ok": True, "imports": history}
