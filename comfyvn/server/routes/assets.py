"""Asset registry API endpoints exposed via FastAPI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, validator

from comfyvn.registry.rebuild import RebuildSummary, audit_sidecars, rebuild_from_disk
from comfyvn.studio.core.asset_registry import AssetRegistry

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["Assets"])
_REGISTRY = AssetRegistry()


def _flatten_tags(values: Optional[Iterable[str]]) -> List[str]:
    tags: List[str] = []
    if not values:
        return tags
    for value in values:
        if value is None:
            continue
        for chunk in str(value).split(","):
            candidate = chunk.strip()
            if candidate:
                tags.append(candidate)
    return tags


def _filter_by_license(
    assets: List[Dict[str, Any]], license_value: Optional[str]
) -> List[Dict[str, Any]]:
    if not license_value:
        return assets
    needle = license_value.strip().lower()
    filtered: List[Dict[str, Any]] = []
    for asset in assets:
        meta = asset.get("meta") or {}
        license_tag = ""
        if isinstance(meta, dict):
            license_tag = str(meta.get("license") or "")
        if license_tag.strip().lower() == needle:
            filtered.append(asset)
    return filtered


def _serialize_summary(summary: RebuildSummary) -> Dict[str, Any]:
    payload = summary.as_dict()
    payload.update(
        {
            "assets_root": str(summary.assets_root),
            "thumb_root": str(summary.thumb_root),
        }
    )
    return payload


class AssetSearchResponse(BaseModel):
    ok: bool = True
    total: int
    items: List[Dict[str, Any]]
    filters: Dict[str, Any]
    debug: Dict[str, Any] | None = None


class SidecarEnforceRequest(BaseModel):
    fix_missing: bool = Field(
        default=True,
        description="Attempt to auto-write missing sidecar files.",
    )
    overwrite: bool = Field(
        default=False,
        description="Rewrite existing sidecars instead of leaving them untouched.",
    )
    fill_metadata: bool = Field(
        default=True,
        description="Back-fill tag/license metadata in addition to writing sidecars.",
    )


class SidecarEnforceResponse(BaseModel):
    ok: bool = True
    report: Dict[str, Any]


class RegistryRebuildRequest(BaseModel):
    assets_root: Optional[str] = Field(
        default=None,
        description="Optional override for the assets root to scan.",
    )
    db_path: Optional[str] = Field(
        default=None,
        description="Optional override for the SQLite registry path.",
    )
    thumbs_root: Optional[str] = Field(
        default=None,
        description="Optional override for the thumbnail cache root.",
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Project identifier used for registry rows.",
    )
    remove_stale: bool = Field(
        default=True,
        description="Remove entries for files that no longer exist on disk.",
    )
    wait_for_thumbs: bool = Field(
        default=True,
        description="Wait for queued thumbnail generation tasks to complete.",
    )

    @validator("assets_root", "db_path", "thumbs_root", pre=True)
    def _blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class RegistryRebuildResponse(BaseModel):
    ok: bool = True
    summary: Dict[str, Any]


async def _list_assets_async(
    *,
    asset_type: Optional[str],
    tags: Optional[List[str]],
    text: Optional[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    return await run_in_threadpool(
        _REGISTRY.list_assets,
        asset_type=asset_type,
        tags=tags,
        text=text,
        limit=limit,
    )


@router.get("/api/assets/search", response_model=AssetSearchResponse)
async def search_assets(
    asset_type: Optional[str] = Query(
        default=None,
        alias="type",
        description="Filter by asset type/folder.",
    ),
    tags: Optional[List[str]] = Query(
        default=None,
        alias="tags",
        description="Comma-separated or repeated tag filters.",
    ),
    tag: Optional[List[str]] = Query(
        default=None,
        alias="tag",
        description="Alternative form for tag filters.",
    ),
    license_tag: Optional[str] = Query(
        default=None,
        alias="license",
        description="Filter by license identifier.",
    ),
    text: Optional[str] = Query(
        default=None,
        description="Substring search that scans path and metadata text.",
    ),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        le=500,
        description="Optional limit for the number of returned rows.",
    ),
    include_debug: bool = Query(
        default=False,
        description="Include registry hook/debug metadata in the response.",
    ),
) -> AssetSearchResponse:
    tag_filters = _flatten_tags(tags) + _flatten_tags(tag)
    normalized_tags = tag_filters or None

    # When filtering on license we need to defer limiting so the client receives
    # up to ``limit`` results that actually match the license constraint.
    raw_limit = limit
    query_limit = None if license_tag else limit
    assets = await _list_assets_async(
        asset_type=asset_type,
        tags=normalized_tags,
        text=text,
        limit=query_limit,
    )
    filtered = _filter_by_license(assets, license_tag)
    if raw_limit:
        filtered = filtered[:raw_limit]

    debug_payload: Optional[Dict[str, Any]] = None
    if include_debug:
        hook_snapshot = _REGISTRY.iter_hooks()
        debug_payload = {
            "hooks": {
                event: [repr(callback) for callback in callbacks]
                for event, callbacks in hook_snapshot.items()
            },
            "assets_root": str(_REGISTRY.ASSETS_ROOT),
            "thumb_root": str(_REGISTRY.THUMB_ROOT),
            "project_id": _REGISTRY.project_id,
        }

    return AssetSearchResponse(
        total=len(filtered),
        items=filtered,
        filters={
            "type": asset_type,
            "tags": normalized_tags or [],
            "license": license_tag,
            "text": text,
            "limit": raw_limit,
        },
        debug=debug_payload,
    )


@router.post("/api/assets/enforce", response_model=SidecarEnforceResponse)
async def enforce_sidecars(payload: SidecarEnforceRequest) -> SidecarEnforceResponse:
    report = await run_in_threadpool(
        audit_sidecars,
        _REGISTRY,
        fix_missing=payload.fix_missing,
        overwrite=payload.overwrite,
        fill_metadata=payload.fill_metadata,
    )
    return SidecarEnforceResponse(report=report.as_dict())


@router.post("/api/assets/rebuild", response_model=RegistryRebuildResponse)
async def rebuild_registry(payload: RegistryRebuildRequest) -> RegistryRebuildResponse:
    assets_root = (
        Path(payload.assets_root).expanduser()
        if payload.assets_root
        else _REGISTRY.ASSETS_ROOT
    )
    db_path = (
        Path(payload.db_path).expanduser()
        if payload.db_path
        else Path(_REGISTRY.db_path)
    )
    thumbs_root = (
        Path(payload.thumbs_root).expanduser()
        if payload.thumbs_root
        else _REGISTRY.THUMB_ROOT
    )
    project_id = payload.project_id or _REGISTRY.project_id

    def _do_rebuild() -> RebuildSummary:
        return rebuild_from_disk(
            assets_root=assets_root,
            db_path=db_path,
            thumbs_root=thumbs_root,
            project_id=project_id,
            remove_stale=payload.remove_stale,
            wait_for_thumbs=payload.wait_for_thumbs,
        )

    try:
        summary = await run_in_threadpool(_do_rebuild)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Asset registry rebuild failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RegistryRebuildResponse(summary=_serialize_summary(summary))
