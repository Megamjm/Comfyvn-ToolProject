from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import time
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from PySide6.QtGui import QAction
from fastapi import APIRouter, Body, HTTPException

from comfyvn.config.runtime_paths import settings_file
from comfyvn.core.comfyui_client import ComfyUIClient
from comfyvn.core.gpu_manager import get_gpu_manager
from comfyvn.core.task_registry import task_registry
from comfyvn.studio.core import AssetRegistry

# comfyvn/server/modules/playground_api.py

router = APIRouter()
PRJ = Path("data/playground")

LOGGER = logging.getLogger(__name__)

CONFIG_FILE = settings_file("comfyui_connector.json")
_DEFAULT_CONFIG: Dict[str, Any] = {
    "base_url": "http://127.0.0.1:8188",
    "timeout": 180.0,
    "poll_interval": 1.5,
    "submit_timeout": 30.0,
    "history_timeout": 15.0,
    "download_timeout": 60.0,
    "health_timeout": 0.8,
}
_config_cache: Dict[str, Any] | None = None
_config_lock = threading.Lock()

_asset_registry = AssetRegistry()
_gpu_manager = get_gpu_manager()


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------
def _default_config() -> Dict[str, Any]:
    return dict(_DEFAULT_CONFIG)


def _normalize_config(data: Dict[str, Any]) -> Dict[str, Any]:
    cfg = _default_config()
    for key, value in data.items():
        if key not in cfg:
            continue
        if key == "base_url":
            cfg["base_url"] = str(value or "").strip()
        else:
            try:
                cfg[key] = float(value)
            except (TypeError, ValueError):
                LOGGER.debug("Ignoring invalid numeric config for %s: %r", key, value)
    base = cfg["base_url"]
    cfg["base_url"] = base.rstrip("/") if base else ""
    if cfg["poll_interval"] <= 0:
        cfg["poll_interval"] = _DEFAULT_CONFIG["poll_interval"]
    if cfg["timeout"] <= 0:
        cfg["timeout"] = _DEFAULT_CONFIG["timeout"]
    return cfg


def _save_config(config: Dict[str, Any]) -> Dict[str, Any]:
    global _config_cache
    payload = _normalize_config(config)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _config_cache = dict(payload)
    return dict(payload)


def _load_config() -> Dict[str, Any]:
    global _config_cache
    with _config_lock:
        if _config_cache is not None:
            return dict(_config_cache)
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("config root must be an object")
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("ComfyUI connector config invalid (%s); resetting to defaults", exc)
                data = {}
        else:
            data = {}
        cfg = _normalize_config(data)
        cached = _save_config(cfg)
        return cached


def _update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    current = _load_config()
    current.update(updates)
    return _save_config(current)


# ---------------------------------------------------------------------------
# Task helpers
# ---------------------------------------------------------------------------
def _task_meta(task_id: str) -> Dict[str, Any]:
    task = task_registry.get(task_id)
    if not task or not task.meta:
        return {}
    return dict(task.meta)


def _serialize_task(task) -> Dict[str, Any]:
    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "meta": task.meta,
    }


def _safe_filename(value: Optional[str], *, fallback: str) -> str:
    name = Path(str(value or "")).name
    return name or fallback


def _parse_object(value: Any, *, name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name} must be JSON object: {exc}") from exc
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"{name} must be an object or JSON string")


def _build_replacements(context: Dict[str, Any]) -> Dict[str, str]:
    replacements: Dict[str, str] = {}
    for key, value in context.items():
        if isinstance(value, (list, tuple, set)):
            replacements[key] = ", ".join(str(item) for item in value)
        elif value is None:
            replacements[key] = ""
        else:
            replacements[key] = str(value)
    return replacements


def _apply_replacements(payload: Any, replacements: Dict[str, str]) -> Any:
    if isinstance(payload, dict):
        return {k: _apply_replacements(v, replacements) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_apply_replacements(item, replacements) for item in payload]
    if isinstance(payload, str):
        result = payload
        for token, value in replacements.items():
            result = result.replace(f"{{{{{token}}}}}", value)
        return result
    return payload


def _prepare_workflow(raw_workflow: Any, *, context: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    label = "inline"
    if isinstance(raw_workflow, dict):
        workflow = copy.deepcopy(raw_workflow)
    elif isinstance(raw_workflow, str):
        candidate = raw_workflow.strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            workflow_path = Path(candidate).expanduser()
            if not workflow_path.exists():
                raise FileNotFoundError(f"workflow file not found: {workflow_path}")
            label = workflow_path.name
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        else:
            if not isinstance(parsed, dict):
                raise ValueError("workflow JSON must be an object at top level")
            workflow = parsed
    else:
        raise ValueError("workflow must be a JSON object or path string")

    if context:
        workflow = _apply_replacements(workflow, _build_replacements(context))
    return workflow, label


def _hash_workflow(workflow: Dict[str, Any]) -> str:
    try:
        serialized = json.dumps(workflow, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        serialized = "{}"
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _extract_history_record(history: Dict[str, Any], prompt_id: str) -> Optional[Dict[str, Any]]:
    if not history:
        return None
    record: Optional[Dict[str, Any]] = None
    if isinstance(history.get("history"), dict):
        record = history["history"].get(prompt_id)
    if record is None:
        maybe = history.get(prompt_id)
        if isinstance(maybe, dict):
            record = maybe
    return record


def _collect_outputs(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    outputs: List[Dict[str, Any]] = []
    raw_outputs = record.get("outputs")
    if not isinstance(raw_outputs, dict):
        return outputs
    for node_id, node_outputs in raw_outputs.items():
        entries: Iterable[Any]
        if isinstance(node_outputs, dict):
            entries = []
            for value in node_outputs.values():
                if isinstance(value, list):
                    entries = list(value)
                    break
        elif isinstance(node_outputs, list):
            entries = node_outputs
        else:
            continue
        for entry in entries:
            if isinstance(entry, dict):
                item = dict(entry)
                item.setdefault("node_id", node_id)
                outputs.append(item)
    return outputs


def _asset_type_for(kind: str, entry_type: str) -> str:
    etype = (entry_type or "").lower()
    if kind == "tts" or etype in {"audio", "wav"}:
        return "comfyui.audio"
    if kind == "lora" or etype in {"model", "checkpoint", "weights"}:
        return "comfyui.lora"
    if etype in {"image", "mask", "latent", "depth", "alpha"}:
        return "comfyui.image"
    return f"comfyui.{kind}"


def _download_and_register_asset(
    client: ComfyUIClient,
    *,
    base_url: str,
    prompt_id: str,
    entry: Dict[str, Any],
    kind: str,
    request_meta: Dict[str, Any],
) -> Dict[str, Any]:
    filename = _safe_filename(entry.get("filename"), fallback=f"{kind}_{uuid.uuid4().hex}.bin")
    params = {
        "filename": entry.get("filename"),
        "subfolder": entry.get("subfolder") or "",
        "type": entry.get("type") or "output",
    }
    try:
        response = client.session.get(
            f"{client.base}/view",
            params=params,
            timeout=_load_config()["download_timeout"],
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"failed to download ComfyUI output {filename}: {exc}") from exc

    suffix = Path(filename).suffix or ".bin"
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(response.content)
        tmp_path = Path(tmp.name)
    try:
        asset_type = _asset_type_for(kind, entry.get("type", ""))
        dest = Path("comfyui") / kind / f"{prompt_id}_{filename}"
        metadata = {
            "source": "comfyui.connector",
            "kind": kind,
            "prompt_id": prompt_id,
            "base_url": base_url,
            "request": request_meta,
            "comfyui": {
                "filename": entry.get("filename"),
                "subfolder": entry.get("subfolder"),
                "type": entry.get("type"),
                "width": entry.get("width"),
                "height": entry.get("height"),
                "format": entry.get("format"),
                "node_id": entry.get("node_id"),
            },
        }
        provenance = {
            "source": "comfyui.connector",
            "inputs": {
                "prompt_id": prompt_id,
                "base_url": base_url,
                "node_id": entry.get("node_id"),
                "type": entry.get("type"),
            },
        }
        asset = _asset_registry.register_file(
            tmp_path,
            asset_type=asset_type,
            dest_relative=dest,
            metadata=metadata,
            copy=True,
            provenance=provenance,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    return asset


def _fail_job(task_id: str, message: str, *, stage: str, error: Optional[Exception] = None) -> None:
    meta = _task_meta(task_id)
    connector_meta = meta.setdefault("connector", {})
    errors = connector_meta.setdefault("errors", [])
    errors.append(
        {
            "stage": stage,
            "message": message,
            "timestamp": time.time(),
        }
    )
    if error:
        connector_meta["last_exception"] = repr(error)
    meta["connector"] = connector_meta
    task_registry.update(task_id, status="error", progress=1.0, message=message, meta=meta)


def _register_outputs(
    task_id: str,
    client: ComfyUIClient,
    *,
    base_url: str,
    prompt_id: str,
    record: Dict[str, Any],
    kind: str,
    request_meta: Dict[str, Any],
    outputs_filter: Optional[Iterable[str]],
    connector_meta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    outputs = _collect_outputs(record)
    if outputs_filter:
        desired = {str(item).lower() for item in outputs_filter if item}
        outputs = [entry for entry in outputs if str(entry.get("type") or "").lower() in desired]

    connector_meta["outputs"] = [
        {
            "filename": entry.get("filename"),
            "type": entry.get("type"),
            "node_id": entry.get("node_id"),
        }
        for entry in outputs
    ]

    if not outputs:
        raise RuntimeError("ComfyUI workflow produced no downloadable outputs")

    assets: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    for entry in outputs:
        if not entry.get("filename"):
            continue
        try:
            asset = _download_and_register_asset(
                client,
                base_url=base_url,
                prompt_id=prompt_id,
                entry=entry,
                kind=kind,
                request_meta=request_meta,
            )
            assets.append(asset)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to register ComfyUI output %s: %s", entry.get("filename"), exc)
            warnings.append(
                {
                    "filename": entry.get("filename"),
                    "type": entry.get("type"),
                    "error": str(exc),
                }
            )

    if warnings:
        connector_meta.setdefault("warnings", []).extend(warnings)
    if not assets:
        raise RuntimeError("ComfyUI outputs could not be downloaded")
    return assets


def _wait_for_prompt(
    task_id: str,
    client: ComfyUIClient,
    *,
    prompt_id: str,
    config: Dict[str, Any],
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    deadline = time.monotonic() + config["timeout"]
    poll_interval = max(config["poll_interval"], 0.25)
    progress = 0.2
    last_status = "queued"
    while time.monotonic() < deadline:
        try:
            history = client.get_history(prompt_id, timeout=config["history_timeout"])
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {404, 422}:
                history = {}
            else:
                raise
        except requests.RequestException:
            history = {}

        record = _extract_history_record(history, prompt_id)
        if record:
            status = str(record.get("status") or "").lower()
            if status in {"completed", "success", "finished"}:
                task_registry.update(
                    task_id,
                    progress=0.95,
                    message="ComfyUI workflow finished; processing outputs…",
                    meta=meta,
                )
                return record
            if status in {"failed", "error", "canceled"}:
                detail = record.get("status_message") or record.get("error") or status
                raise RuntimeError(f"ComfyUI workflow failed: {detail}")
            last_status = status or last_status
        progress = min(0.9, progress + 0.05)
        task_registry.update(
            task_id,
            progress=progress,
            message=f"Waiting on ComfyUI ({last_status})…",
            meta=meta,
        )
        time.sleep(poll_interval)

    raise TimeoutError(f"ComfyUI workflow timeout after {config['timeout']}s")


def _run_pipeline_job(task_id: str, options: Dict[str, Any]) -> List[Dict[str, Any]]:
    config = _load_config()
    base_url = options.get("base_url") or config["base_url"]
    if not base_url:
        _fail_job(task_id, "ComfyUI connector base_url not configured", stage="configure")
        return []

    client = ComfyUIClient(base_url)
    kind = options.get("kind", "image")
    request_meta = options.get("request_meta", {})
    workflow = options["workflow"]
    meta = _task_meta(task_id)
    connector_meta = meta.setdefault("connector", {})
    connector_meta.update(
        {
            "kind": kind,
            "base_url": base_url,
            "client_id": options.get("client_id"),
            "workflow_hash": options.get("workflow_hash"),
            "workflow_label": options.get("workflow_label"),
            "requested_at": time.time(),
            "request": request_meta,
        }
    )

    payload_meta = meta.get("payload")
    if isinstance(payload_meta, dict):
        connector_meta.setdefault("device", payload_meta.get("device"))
        connector_meta.setdefault("compute_policy", payload_meta.get("meta", {}).get("compute_policy"))

    meta["connector"] = connector_meta
    task_registry.update(
        task_id,
        status="running",
        progress=0.05,
        message="Submitting ComfyUI workflow…",
        meta=meta,
    )

    workflow_payload = copy.deepcopy(workflow)
    workflow_payload.setdefault("client_id", options.get("client_id") or uuid.uuid4().hex)

    try:
        response = client.queue_prompt(workflow_payload, timeout=config["submit_timeout"])
    except requests.RequestException as exc:
        LOGGER.warning("ComfyUI submission failed: %s", exc)
        _fail_job(task_id, f"Failed to submit workflow: {exc}", stage="submit", error=exc)
        return []

    prompt_id = response.get("prompt_id")
    if not prompt_id:
        _fail_job(task_id, "ComfyUI did not return a prompt_id", stage="submit")
        return []

    connector_meta["prompt_id"] = prompt_id
    meta["connector"] = connector_meta
    task_registry.update(
        task_id,
        progress=0.15,
        message="Workflow submitted; waiting on ComfyUI…",
        meta=meta,
    )

    try:
        record = _wait_for_prompt(task_id, client, prompt_id=prompt_id, config=config, meta=meta)
    except TimeoutError as exc:
        LOGGER.warning("ComfyUI workflow timeout job=%s: %s", task_id, exc)
        _fail_job(task_id, str(exc), stage="wait", error=exc)
        return []
    except RuntimeError as exc:
        LOGGER.warning("ComfyUI workflow failure job=%s: %s", task_id, exc)
        _fail_job(task_id, str(exc), stage="wait", error=exc)
        return []
    except requests.RequestException as exc:
        LOGGER.warning("ComfyUI history fetch failed job=%s: %s", task_id, exc)
        _fail_job(task_id, f"Failed to poll ComfyUI history: {exc}", stage="wait", error=exc)
        return []

    outputs_filter = options.get("outputs")
    try:
        assets = _register_outputs(
            task_id,
            client,
            base_url=base_url,
            prompt_id=prompt_id,
            record=record,
            kind=kind,
            request_meta=request_meta,
            outputs_filter=outputs_filter,
            connector_meta=connector_meta,
        )
    except Exception as exc:
        LOGGER.warning("ComfyUI output processing failed job=%s: %s", task_id, exc)
        _fail_job(task_id, f"Failed to capture ComfyUI outputs: {exc}", stage="outputs", error=exc)
        return []

    connector_meta["assets"] = [
        {"uid": asset.get("uid"), "path": asset.get("path"), "type": asset.get("type")}
        for asset in assets
    ]
    connector_meta["completed_at"] = time.time()
    meta["connector"] = connector_meta

    task_registry.update(
        task_id,
        status="done",
        progress=1.0,
        message=options.get("success_message") or f"ComfyUI {kind} workflow complete",
        meta=meta,
    )
    LOGGER.info("ComfyUI job complete job=%s assets=%d", task_id, len(assets))
    return assets


def _run_pipeline_job_safe(task_id: str, options: Dict[str, Any]) -> None:
    try:
        _run_pipeline_job(task_id, options)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Unhandled error in ComfyUI connector job %s: %s", task_id, exc)
        _fail_job(task_id, "Unhandled connector error", stage="internal", error=exc)


def _spawn_pipeline_job(task_id: str, options: Dict[str, Any]) -> None:
    thread = threading.Thread(
        target=_run_pipeline_job_safe,
        args=(task_id, options),
        name=f"ComfyUIPipeline-{task_id[:8]}",
        daemon=True,
    )
    thread.start()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@router.get("/health")
def health() -> Dict[str, Any]:
    cfg = _load_config()
    ok = PRJ.exists()
    comfy_state = {"configured": bool(cfg["base_url"]), "base_url": cfg["base_url"], "online": False}
    if cfg["base_url"]:
        client = ComfyUIClient(cfg["base_url"])
        comfy_state["online"] = client.health(timeout=cfg["health_timeout"])
    return {
        "ok": True,
        "engine": "godot",
        "project_dir": str(PRJ),
        "present": ok,
        "comfy": comfy_state,
    }


@router.get("/recommend")
def recommend() -> Dict[str, Any]:
    return {
        "ok": True,
        "engines": [
            {"name": "Godot", "why": "Open-source, lightweight 3D/2D, good for preview"},
            {"name": "Blend4Web/Three.js", "why": "Web preview alternative"},
        ],
    }


@router.get("/playground/comfy/config")
def get_connector_config() -> Dict[str, Any]:
    return {"ok": True, "config": _load_config()}


@router.post("/playground/comfy/config")
def update_connector_config(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    try:
        config = _update_config(payload)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "config": config}


@router.get("/playground/comfy/health")
def comfy_health() -> Dict[str, Any]:
    cfg = _load_config()
    if not cfg["base_url"]:
        return {"ok": False, "configured": False, "message": "base_url not set"}
    client = ComfyUIClient(cfg["base_url"])
    ready = client.health(timeout=cfg["health_timeout"])
    return {
        "ok": ready,
        "configured": True,
        "base_url": cfg["base_url"],
    }


@router.post("/playground/comfy/pipelines")
def submit_pipeline(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    cfg = _load_config()
    if not cfg["base_url"]:
        raise HTTPException(status_code=400, detail="ComfyUI connector not configured (base_url missing)")

    raw_workflow = payload.get("workflow") or payload.get("graph")
    if raw_workflow is None:
        raw_workflow = payload.get("workflow_path") or payload.get("workflow_file")
    if raw_workflow is None:
        raise HTTPException(status_code=400, detail="workflow or workflow_path is required")

    try:
        context = _parse_object(payload.get("context"), name="context")
        metadata = _parse_object(payload.get("metadata"), name="metadata")
        requirements = _parse_object(payload.get("requirements"), name="requirements")
        workflow, workflow_label = _prepare_workflow(raw_workflow, context=context)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    workflow_hash = _hash_workflow(workflow)
    kind = str(payload.get("kind") or "image").strip().lower()
    outputs_filter = payload.get("outputs")
    if isinstance(outputs_filter, str):
        outputs_filter = [outputs_filter]
    elif isinstance(outputs_filter, (list, tuple)):
        outputs_filter = [str(item) for item in outputs_filter if item]
    else:
        outputs_filter = None

    label = payload.get("label") or f"ComfyUI {kind} pipeline"
    client_id = uuid.uuid4().hex
    request_meta = {
        "metadata": metadata,
        "context": context,
        "kind": kind,
        "workflow_label": workflow_label,
    }

    registry_payload = {
        "kind": kind,
        "workflow": workflow_label,
        "requirements": requirements,
        "metadata": metadata,
    }
    task_id = task_registry.register(
        f"comfyui.{kind}",
        registry_payload,
        message=label,
        meta={
            "connector": {
                "base_url": cfg["base_url"],
                "workflow_hash": workflow_hash,
                "workflow_label": workflow_label,
            },
            "request": request_meta,
        },
    )

    options = {
        "workflow": workflow,
        "workflow_label": workflow_label,
        "workflow_hash": workflow_hash,
        "base_url": cfg["base_url"],
        "kind": kind,
        "client_id": client_id,
        "metadata": metadata,
        "context": context,
        "outputs": outputs_filter,
        "request_meta": request_meta,
        "success_message": payload.get("success_message"),
    }

    blocking = bool(payload.get("blocking", False))
    if blocking:
        assets = _run_pipeline_job(task_id, options)
        task = task_registry.get(task_id)
        if task and task.status == "error":
            raise HTTPException(status_code=502, detail=task.message or "ComfyUI workflow failed")
        return {"ok": True, "job": _serialize_task(task), "assets": assets}

    _spawn_pipeline_job(task_id, options)
    return {"ok": True, "job": {"id": task_id}}


@router.post("/playground/comfy/pipelines/{kind}")
def submit_pipeline_short(kind: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    payload = dict(payload or {})
    payload.setdefault("kind", kind)
    return submit_pipeline(payload)


@router.get("/playground/comfy/jobs/{task_id}")
def comfy_job_status(task_id: str) -> Dict[str, Any]:
    task = task_registry.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": _serialize_task(task)}


@router.get("/playground/comfy/jobs")
def comfy_job_list() -> Dict[str, Any]:
    jobs = [_serialize_task(task) for task in task_registry.list() if task.kind.startswith("comfyui.")]
    return {"ok": True, "jobs": jobs}
