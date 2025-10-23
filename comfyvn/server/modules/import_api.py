from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from PySide6.QtGui import QAction

from comfyvn.config.runtime_paths import imports_log_dir
from comfyvn.core.policy_gate import policy_gate
from comfyvn.core.task_registry import task_registry
from comfyvn.policy.enforcer import policy_enforcer
from comfyvn.server.core.chat_import import (
    apply_alias_map,
    assign_by_patterns,
    parse_text,
    to_scene_dict,
)
from comfyvn.server.core.import_status import import_status_store
from comfyvn.server.core.manga_importer import MangaImportError, import_manga_archive
from comfyvn.server.modules.auth import require_scope

router = APIRouter()
logger = logging.getLogger("comfyvn.api.imports")

MANGA_LOG_DIR = imports_log_dir() / "manga"
MANGA_LOG_DIR.mkdir(parents=True, exist_ok=True)

SCENE_DIR = Path("./data/scenes")
SCENE_DIR.mkdir(parents=True, exist_ok=True)


def _write_scene(name: str, data: Dict[str, Any]) -> str:
    p = (SCENE_DIR / f"{name}.json").resolve()
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return name


def _log_manga(log_file: Optional[Path], message: str) -> None:
    if not log_file:
        return
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    try:
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except Exception:
        logger.debug("Failed to write manga import log line", exc_info=True)


def _build_manga_preview(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    import_id = summary.get("import_id")
    if not import_id:
        return None
    converted_dir = summary.get("converted_path")
    preview_root: Optional[Path] = None
    if converted_dir:
        try:
            preview_root = (
                Path(converted_dir).expanduser().resolve().parent.parent / "preview"
            )
        except Exception:
            preview_root = None
    if preview_root is None:
        data_root = Path(summary.get("data_root") or "data").expanduser().resolve()
        preview_root = data_root / "imports" / "manga" / "preview"
    preview_root.mkdir(parents=True, exist_ok=True)
    preview_payload = {
        "import_id": import_id,
        "scenes": list(summary.get("scenes") or [])[:3],
        "characters": list(summary.get("characters") or [])[:6],
        "panels": list(summary.get("panels") or [])[:5],
        "advisories": list(summary.get("advisories") or []),
        "translation": summary.get("translation"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    preview_path = preview_root / f"{import_id}.json"
    try:
        preview_path.write_text(
            json.dumps(preview_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        summary["preview_path"] = preview_path.as_posix()
        summary["preview"] = preview_payload
    except Exception:
        logger.debug("Failed to write manga preview for %s", import_id, exc_info=True)
    return preview_payload


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


def _execute_manga_import(
    task_id: str, archive: str, options: Dict[str, Any], log_path: Optional[str] = None
) -> Dict[str, Any]:
    log_file = Path(log_path).expanduser().resolve() if log_path else None
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.touch(exist_ok=True)
    _log_manga(log_file, f"Starting manga import '{task_id}' from {archive}")

    logger.info("[Manga Import] job=%s starting -> %s", task_id, archive)
    task_registry.update(
        task_id, status="running", progress=0.05, message="Preparing manga import"
    )
    try:
        meta_payload: Dict[str, Any] = {"archive": archive}
        for key, value in options.items():
            if isinstance(value, Path):
                meta_payload[key] = value.as_posix()
            else:
                meta_payload[key] = value
        import_status_store.update(
            task_id,
            state="running",
            percent=5.0,
            message="Preparing manga import",
            stage="init",
            meta=meta_payload,
        )
    except KeyError:
        pass

    try:
        summary = import_manga_archive(archive, **options)
        _log_manga(log_file, "Archive processed successfully")
    except MangaImportError as exc:
        meta = _task_meta(task_id)
        meta["error"] = str(exc)
        task_registry.update(
            task_id, status="error", progress=1.0, message=str(exc), meta=meta
        )
        _log_manga(log_file, f"[error] {exc}")
        try:
            import_status_store.update(
                task_id,
                state="error",
                percent=100.0,
                message=str(exc),
                stage="failed",
                meta={"error": str(exc)},
            )
        except KeyError:
            pass
        logger.warning("[Manga Import] job=%s failed: %s", task_id, exc)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        meta = _task_meta(task_id)
        meta["error"] = str(exc)
        task_registry.update(
            task_id,
            status="error",
            progress=1.0,
            message="manga import failed",
            meta=meta,
        )
        _log_manga(log_file, f"[error] {exc}")
        try:
            import_status_store.update(
                task_id,
                state="error",
                percent=100.0,
                message="manga import failed",
                stage="failed",
                meta={"error": str(exc)},
            )
        except KeyError:
            pass
        logger.exception("[Manga Import] job=%s failed unexpectedly", task_id)
        raise

    preview_payload = _build_manga_preview(summary)
    if preview_payload:
        _log_manga(
            log_file,
            f"Preview generated ({len(preview_payload.get('panels', []))} panels)",
        )
    if log_file:
        summary["logs_path"] = log_file.as_posix()

    stats = (
        f"scenes={len(summary.get('scenes', []))} "
        f"assets={len(summary.get('assets', []))} "
        f"characters={len(summary.get('characters', []))}"
    )
    meta = _task_meta(task_id)
    meta["result"] = summary
    meta["summary_path"] = summary.get("summary_path")
    meta["preview_path"] = summary.get("preview_path")
    meta["logs_path"] = summary.get("logs_path")
    task_registry.update(
        task_id,
        status="done",
        progress=1.0,
        message=f"Manga import complete ({stats})",
        meta=meta,
    )
    try:
        import_status_store.update(
            task_id,
            state="done",
            percent=100.0,
            message=f"Manga import complete ({stats})",
            stage="completed",
            meta={
                "summary_path": summary.get("summary_path"),
                "preview_path": summary.get("preview_path"),
            },
        )
    except KeyError:
        pass
    _log_manga(log_file, f"[ok] {stats}")
    logger.info("[Manga Import] job=%s complete %s", task_id, stats)
    return summary


def _spawn_manga_job(
    task_id: str, archive: str, options: Dict[str, Any], log_path: Optional[str] = None
) -> None:
    def _runner() -> None:
        try:
            _execute_manga_import(task_id, archive, options, log_path=log_path)
        except MangaImportError:
            return
        except Exception:
            return

    threading.Thread(
        target=_runner, name=f"MangaImport-{task_id[:8]}", daemon=True
    ).start()


@router.post("/chat")
async def import_chat(
    body: Dict[str, Any], _: bool = Depends(require_scope(["content.write"]))
):
    gate = policy_gate.evaluate_action("import.chat")
    if gate.get("requires_ack"):
        logger.warning("Advisory disclaimer pending for import.chat")
    text = str(body.get("text") or "")
    if not text.strip():
        raise HTTPException(status_code=400, detail="text required")
    fmt = str(body.get("format") or "auto")
    base = str(body.get("name") or f"scene_{uuid.uuid4().hex[:8]}")
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
                if current:
                    scenes.append(current)
                    current = []
                continue
            current.append(ln)
        if current:
            scenes.append(current)
    elif max_lines and max_lines > 0:
        current: List[dict] = []
        for ln in lines:
            current.append(ln)
            if len(current) >= max_lines:
                scenes.append(current)
                current = []
        if current:
            scenes.append(current)
    else:
        scenes = [lines]

    scene_payloads: Dict[str, Dict[str, Any]] = {}
    scene_paths: Dict[str, Path] = {}
    for i, seq in enumerate(scenes):
        name = base if len(scenes) == 1 else f"{base}_{i+1:02d}"
        data = to_scene_dict(name, seq)
        scene_payloads[name] = data
        scene_paths[name] = (SCENE_DIR / f"{name}.json").resolve()

    bundle_payload = {
        "project_id": body.get("project_id"),
        "timeline_id": body.get("timeline_id"),
        "scenes": scene_payloads,
        "scene_sources": {key: path.as_posix() for key, path in scene_paths.items()},
        "licenses": body.get("licenses") or [],
        "metadata": {
            "source": "import.chat",
            "import_name": base,
            "split_on": split_on or None,
            "project_id": body.get("project_id"),
        },
    }
    enforcement = policy_enforcer.enforce(
        "import.chat",
        bundle_payload,
        source="import.chat",
    )
    if not enforcement.allow:
        raise HTTPException(
            status_code=423,
            detail={
                "message": "policy enforcement blocked",
                "result": enforcement.to_dict(),
            },
        )

    created: List[str] = []
    for name, data in scene_payloads.items():
        _write_scene(name, data)
        created.append(name)

    return {
        "ok": True,
        "created": created,
        "count": len(created),
        "gate": gate,
        "enforcement": enforcement.to_dict(),
    }


@router.post("/manga/import")
async def manga_import(
    payload: Dict[str, Any], _: bool = Depends(require_scope(["content.write"], cost=5))
):
    gate = policy_gate.evaluate_action("import.manga")
    if gate.get("requires_ack"):
        logger.warning("Advisory disclaimer pending for import.manga")
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
    log_path = MANGA_LOG_DIR / f"manga_{task_id}.log"
    log_path.touch(exist_ok=True)

    task = task_registry.get(task_id)
    base_meta = dict(getattr(task, "meta", {}) or {})
    base_meta.update(
        {
            "archive": str(archive_path),
            "project_id": options.get("project_id"),
            "logs_path": log_path.as_posix(),
        }
    )
    task_registry.update(task_id, meta=base_meta)

    status_links = {"logs": f"/jobs/logs/{task_id}"}
    status_meta = {
        "archive": str(archive_path),
        "project_id": options.get("project_id"),
        "translation_enabled": options.get("translation_enabled"),
        "translation_lang": options.get("translation_lang"),
    }
    try:
        import_status_store.register(
            "manga",
            task_id,
            task_id=task_id,
            logs_path=log_path.as_posix(),
            links=status_links,
            meta=status_meta,
        )
    except Exception:  # pragma: no cover - defensive
        logger.debug(
            "Failed to register manga import status for %s", task_id, exc_info=True
        )

    if blocking:
        try:
            summary = _execute_manga_import(
                task_id, str(archive_path), options, log_path=log_path.as_posix()
            )
        except MangaImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=500, detail="manga import failed") from exc
        return {
            "ok": True,
            "import": summary,
            "job": {"id": task_id},
            "logs_path": log_path.as_posix(),
        }

    try:
        _spawn_manga_job(
            task_id, str(archive_path), options, log_path=log_path.as_posix()
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to spawn manga import job: %s", exc)
        raise HTTPException(
            status_code=500, detail="manga import spawn failed"
        ) from exc

    return {
        "ok": True,
        "job": {"id": task_id},
        "logs_path": log_path.as_posix(),
        "links": {"logs": f"/jobs/logs/{task_id}"},
        "gate": gate,
    }


@router.get("/manga/import/{job_id}")
async def manga_import_status(
    job_id: str, _: bool = Depends(require_scope(["content.read"], cost=1))
):
    task = task_registry.get(job_id)
    if not task:
        raise HTTPException(status_code=404, detail="job not found")
    summary = _load_summary_from_meta(task.meta or {})
    return {"ok": True, "job": _serialize_task(task), "summary": summary}


@router.get("/manga/imports/history")
async def manga_import_history(
    limit: int = 20, _: bool = Depends(require_scope(["content.read"], cost=1))
):
    limit = max(1, min(int(limit), 200))
    history = _load_manga_history(limit)
    return {"ok": True, "imports": history}
