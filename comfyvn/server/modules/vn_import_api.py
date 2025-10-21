from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from comfyvn.core.task_registry import task_registry
from comfyvn.server.core.external_extractors import extractor_manager
from comfyvn.server.core import extractor_installer
from comfyvn.server.core.vn_importer import VNImportError, import_vn_package
from comfyvn.server.modules.auth import require_scope


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vn", tags=["Importers"])


def _task_meta(task_id: str) -> Dict[str, Any]:
    task = task_registry.get(task_id)
    if task and task.meta:
        return dict(task.meta)
    return {}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered in {"true", "1", "yes", "on"}
    return bool(value)


def _execute_import(task_id: str, package_path: str, overwrite: bool, tool: Optional[str]) -> Dict[str, Any]:
    logger.info(
        "[VN Import] job=%s starting (overwrite=%s, tool=%s) -> %s",
        task_id,
        overwrite,
        tool,
        package_path,
    )
    task_registry.update(task_id, status="running", progress=0.05, message="Preparing import")
    try:
        summary = import_vn_package(package_path, overwrite=overwrite, tool=tool)
    except Exception as exc:  # let caller convert to HTTP error, but make sure registry updated first
        meta = _task_meta(task_id)
        meta["error"] = str(exc)
        task_registry.update(task_id, status="error", progress=1.0, message=str(exc), meta=meta)
        logger.exception("[VN Import] job=%s failed: %s", task_id, exc)
        raise

    meta = _task_meta(task_id)
    meta["result"] = summary
    meta["summary_path"] = summary.get("summary_path")
    meta["extractor"] = summary.get("extractor")
    if summary.get("extractor_warning"):
        meta.setdefault("warnings", []).append(summary["extractor_warning"])
    stats = (
        f"adapter={summary.get('adapter', 'generic')} "
        f"extractor={summary.get('extractor') or 'builtin'} "
        f"scenes={len(summary.get('scenes', []))} "
        f"characters={len(summary.get('characters', []))} "
        f"assets={len(summary.get('assets', []))}"
    )
    task_registry.update(
        task_id,
        status="done",
        progress=1.0,
        message=f"Import complete ({stats})",
        meta=meta,
    )
    logger.info("[VN Import] job=%s complete %s", task_id, stats)
    return summary


def _spawn_import_job(task_id: str, package_path: str, overwrite: bool, tool: Optional[str]) -> None:
    def _runner() -> None:
        try:
            _execute_import(task_id, package_path, overwrite, tool)
        except VNImportError:
            # already logged in _execute_import; nothing else to do
            return
        except Exception:
            return

    threading.Thread(target=_runner, name=f"VNImportJob-{task_id[:8]}", daemon=True).start()


@router.post("/import")
async def import_vn(payload: Dict[str, Any]):
    """Import a ComfyVN package (.cvnpack/.zip/.pak) into the local workspace."""

    path_value = payload.get("path") or payload.get("package_path")
    if not path_value:
        raise HTTPException(status_code=400, detail="path is required")

    overwrite = bool(payload.get("overwrite", False))
    blocking_value = payload.get("blocking")
    blocking = _coerce_bool(blocking_value) if blocking_value is not None else True
    tool = payload.get("tool")
    if tool:
        tool = str(tool).strip()
    resolved_path = Path(path_value).expanduser()
    logger.info(
        "POST /vn/import path=%s overwrite=%s blocking=%s tool=%s",
        resolved_path,
        overwrite,
        blocking,
        tool,
    )

    task_id = task_registry.register(
        "vn.import",
        {"path": str(resolved_path), "overwrite": overwrite},
        message=f"Import {resolved_path.name}",
        meta={"package": str(resolved_path), "tool": tool},
    )

    if blocking:
        try:
            summary = _execute_import(task_id, str(resolved_path), overwrite, tool)
        except VNImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=500, detail="vn import failed") from exc
        return {"ok": True, "import": summary, "job": {"id": task_id}}

    try:
        _spawn_import_job(task_id, str(resolved_path), overwrite, tool)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to spawn VN import job: %s", exc)
        raise HTTPException(status_code=500, detail="vn import spawn failed") from exc

    return {"ok": True, "job": {"id": task_id}}


@router.get("/import/{job_id}")
async def import_status(job_id: str, _: bool = Depends(require_scope(["content.read"], cost=1))):
    task = task_registry.get(job_id)
    if not task:
        raise HTTPException(status_code=404, detail="job not found")
    summary = _load_summary_from_meta(task.meta or {})
    return {"ok": True, "job": _serialize_task(task), "summary": summary}


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
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load summary from %s: %s", path, exc)
    return None


def _serialize_task(task) -> Dict[str, Any]:
    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "meta": task.meta,
    }


def _data_root() -> Path:
    env = os.getenv("COMFYVN_DATA_ROOT")
    base = Path(env).expanduser() if env else Path("./data")
    return base.resolve()


def _load_history(limit: int = 20) -> List[Dict[str, Any]]:
    root = _data_root() / "imports" / "vn"
    if not root.exists():
        return []
    summaries: List[Dict[str, Any]] = []
    files = sorted(root.glob("*/summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for summary_path in files[:limit]:
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            data.setdefault("summary_path", summary_path.as_posix())
            summaries.append(data)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to read import summary %s: %s", summary_path, exc)
            continue
    return summaries


@router.get("/imports/history")
async def import_history(limit: int = 20, _: bool = Depends(require_scope(["content.read"], cost=1))):
    limit = max(1, min(int(limit), 200))
    history = _load_history(limit)
    return {"ok": True, "imports": history}


def _tool_to_dict(tool) -> Dict[str, Any]:
    return {
        "name": tool.name,
        "path": str(tool.path),
        "extensions": tool.extensions,
        "notes": tool.notes,
        "warning": tool.warning,
    }


@router.get("/tools")
async def list_tools(_: bool = Depends(require_scope(["content.read"], cost=1))):
    tools = [_tool_to_dict(tool) for tool in extractor_manager.list_tools()]
    return {"ok": True, "tools": tools}


@router.post("/tools/register")
async def register_tool(payload: Dict[str, Any], _: bool = Depends(require_scope(["content.write"], cost=5))):
    name = (payload.get("name") or "").strip()
    path_value = payload.get("path") or payload.get("binary")
    if not name or not path_value:
        raise HTTPException(status_code=400, detail="name and path required")

    extensions = payload.get("extensions") or []
    if not isinstance(extensions, list):
        raise HTTPException(status_code=400, detail="extensions must be a list")
    notes = str(payload.get("notes") or "")
    warning = str(payload.get("warning") or "")

    tool_path = Path(path_value).expanduser()
    if not tool_path.exists():
        raise HTTPException(status_code=400, detail="tool path does not exist")

    tool = extractor_manager.register(name, str(tool_path), extensions=extensions, notes=notes, warning=warning)
    return {"ok": True, "tool": _tool_to_dict(tool)}


@router.delete("/tools/{name}")
async def remove_tool(name: str, _: bool = Depends(require_scope(["content.write"], cost=5))):
    if not extractor_manager.unregister(name):
        raise HTTPException(status_code=404, detail="tool not found")
    return {"ok": True}


@router.post("/tools/install")
async def install_tool(payload: Dict[str, Any], _: bool = Depends(require_scope(["content.write"], cost=5))):
    name = (payload.get("name") or "").strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not payload.get("accept_terms"):
        raise HTTPException(status_code=400, detail="accept_terms must be true")
    meta = extractor_installer.KNOWN_EXTRACTORS.get(name)
    if not meta:
        raise HTTPException(status_code=404, detail="unknown extractor")

    target = payload.get("target_dir")
    try:
        result = extractor_installer.install_extractor(name, target_dir=target)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    registered = extractor_manager.register(
        name,
        result["path"],
        extensions=meta.extensions,
        notes=meta.notes,
        warning=meta.warning,
    )
    tool_info = {
        "name": getattr(registered, "name", name),
        "path": getattr(registered, "path", result["path"]),
        "extensions": meta.extensions,
        "warning": meta.warning,
        "license": meta.license,
    }
    return {"ok": True, "tool": tool_info, "notes": meta.notes}


@router.get("/tools/catalog")
async def tool_catalog() -> Dict[str, Any]:
    catalog = []
    for key, meta in extractor_installer.KNOWN_EXTRACTORS.items():
        catalog.append(
            {
                "id": key,
                "name": meta.name,
                "url": meta.url,
                "filename": meta.filename,
                "extensions": meta.extensions,
                "warning": meta.warning,
                "license": meta.license,
                "notes": meta.notes,
            }
        )
    catalog.sort(key=lambda entry: entry["name"].lower())
    return {"ok": True, "tools": catalog}
