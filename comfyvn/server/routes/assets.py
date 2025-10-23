"""Asset registry API endpoints exposed via FastAPI."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

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


def _ensure_relative_path(value: Optional[str]) -> Optional[Path]:
    if value is None:
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(
            status_code=400,
            detail="dest_path must be relative to the asset registry root.",
        )
    return candidate


def _coerce_metadata(meta: Any) -> Dict[str, Any]:
    if meta is None:
        return {}
    if isinstance(meta, dict):
        return dict(meta)
    if isinstance(meta, str):
        text = meta.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - validation
            raise HTTPException(
                status_code=400, detail=f"metadata must be valid JSON: {exc}"
            ) from exc
        if isinstance(parsed, dict):
            return dict(parsed)
        raise HTTPException(
            status_code=400, detail="metadata JSON must decode to an object."
        )
    raise HTTPException(
        status_code=400, detail="metadata must be an object or JSON string."
    )


def _serialize_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    meta_raw = asset.get("meta")
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    links_raw = asset.get("links")
    payload: Dict[str, Any] = {
        "id": asset.get("uid"),
        "uid": asset.get("uid"),
        "type": asset.get("type"),
        "hash": asset.get("hash"),
        "bytes": asset.get("bytes"),
        "tags": list(meta.get("tags") or []),
        "license": meta.get("license"),
        "origin": meta.get("origin"),
        "version": meta.get("version"),
        "created_at": asset.get("created_at"),
        "metadata": meta,
        "links": dict(links_raw) if isinstance(links_raw, dict) else {},
        "sidecar": asset.get("sidecar"),
        "path": asset.get("path"),
    }
    thumb = asset.get("thumb")
    if isinstance(thumb, str):
        payload["thumb"] = thumb
    preview = meta.get("preview")
    if isinstance(preview, dict):
        payload["preview"] = preview
    thumbnails = meta.get("thumbnails")
    if isinstance(thumbnails, dict):
        payload["thumbnails"] = thumbnails
    return payload


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


class AssetRegisterRequest(BaseModel):
    path: str = Field(
        ..., description="Absolute or relative path to the source asset on disk."
    )
    asset_type: str = Field(
        default="generic", description="Logical asset type bucket (e.g. images)."
    )
    dest_path: Optional[str] = Field(
        default=None,
        description="Optional relative destination path inside the asset registry.",
    )
    metadata: Optional[Any] = Field(
        default=None,
        description="Asset metadata object or JSON string to persist in the sidecar.",
    )
    copy_file: bool = Field(
        default=True,
        alias="copy",
        description="Copy the source into the asset registry (set false to register in-place).",
    )


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

    @field_validator("assets_root", "db_path", "thumbs_root", mode="before")
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


@router.post("/api/assets/register")
async def register_asset(payload: AssetRegisterRequest) -> Dict[str, Any]:
    source = Path(payload.path).expanduser()
    if not source.exists():
        raise HTTPException(status_code=404, detail="Source file does not exist.")

    dest_relative = _ensure_relative_path(payload.dest_path)
    if dest_relative and not dest_relative.suffix:
        dest_relative = dest_relative / source.name

    metadata = _coerce_metadata(payload.metadata)
    license_value = metadata.get("license")
    license_tag = license_value.strip() if isinstance(license_value, str) else None
    asset_type = payload.asset_type or "generic"

    def _register() -> Dict[str, Any]:
        return _REGISTRY.register_file(
            source,
            asset_type=asset_type,
            dest_relative=dest_relative,
            metadata=metadata,
            copy=payload.copy_file,
            license_tag=license_tag,
        )

    asset_info = await run_in_threadpool(_register)
    return {
        "ok": True,
        "asset_id": asset_info.get("uid"),
        "asset": _serialize_asset(asset_info),
    }


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
        alias="q",
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
    total_results = len(filtered)
    serialized = [_serialize_asset(asset) for asset in filtered]
    if raw_limit:
        serialized = serialized[:raw_limit]

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
        total=total_results,
        items=serialized,
        filters={
            "type": asset_type,
            "tags": normalized_tags or [],
            "license": license_tag,
            "q": text,
            "limit": raw_limit,
        },
        debug=debug_payload,
    )


@router.get("/api/assets/{uid}")
async def get_asset(uid: str) -> Dict[str, Any]:
    asset = await run_in_threadpool(_REGISTRY.get_asset, uid)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return {"ok": True, "asset": _serialize_asset(asset)}


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
