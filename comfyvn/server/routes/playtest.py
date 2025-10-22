from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

from fastapi import APIRouter, HTTPException

from comfyvn.config import feature_flags
from comfyvn.qa.playtest import HeadlessPlaytestRunner, PlaytestError

router = APIRouter(prefix="/api/playtest", tags=["Playtest"])
_RUNNER = HeadlessPlaytestRunner()


def _normalize_prompt_packs(raw: Any) -> Optional[Sequence[str]]:
    if raw is None:
        return None
    if isinstance(raw, str):
        candidate = raw.strip()
        return [candidate] if candidate else None
    if isinstance(raw, Iterable):
        packs: list[str] = []
        for item in raw:
            if isinstance(item, str):
                candidate = item.strip()
                if candidate:
                    packs.append(candidate)
        return packs or None
    return None


@router.post("/run")
async def playtest_run(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not feature_flags.is_enabled("enable_playtest_harness"):
        raise HTTPException(status_code=403, detail="playtest harness disabled")

    scene = payload.get("scene")
    if not isinstance(scene, Mapping):
        if {"id", "start", "nodes"} <= set(payload.keys()):
            scene = payload
        else:
            raise HTTPException(
                status_code=400, detail="scene payload missing or invalid"
            )

    seed_raw = payload.get("seed", 0)
    try:
        seed_value = int(seed_raw)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail="seed must be numeric") from exc

    variables_raw = payload.get("variables")
    variables_map = variables_raw if isinstance(variables_raw, Mapping) else None

    pov_raw = payload.get("pov")
    pov_value = (
        str(pov_raw).strip() if isinstance(pov_raw, str) and pov_raw.strip() else None
    )

    workflow_raw = payload.get("workflow")
    workflow_value = (
        str(workflow_raw).strip()
        if isinstance(workflow_raw, str) and workflow_raw.strip()
        else None
    )

    prompt_packs = _normalize_prompt_packs(payload.get("prompt_packs"))

    metadata_raw = payload.get("metadata")
    if metadata_raw is None:
        metadata_value = None
    elif isinstance(metadata_raw, Mapping):
        metadata_value = metadata_raw
    else:
        raise HTTPException(status_code=400, detail="metadata must be an object")

    dry_run = bool(payload.get("dry_run", False))
    persist_flag = bool(payload.get("persist", False))
    if dry_run:
        persist_flag = False

    try:
        result = _RUNNER.run(
            scene,
            seed=seed_value,
            variables=variables_map,
            pov=pov_value,
            prompt_packs=prompt_packs,
            workflow=workflow_value,
            persist=persist_flag,
            metadata=metadata_value,
        )
    except PlaytestError as exc:
        detail: dict[str, Any] = {"error": str(exc)}
        if exc.issues:
            detail["issues"] = exc.issues
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    response: dict[str, Any] = {
        "ok": True,
        "digest": result.digest,
        "trace": result.trace,
        "persisted": result.persisted,
        "dry_run": dry_run or not result.persisted,
    }
    if result.trace_path:
        response["trace_path"] = str(result.trace_path)
    if result.log_path:
        response["log_path"] = str(result.log_path)
    return response
