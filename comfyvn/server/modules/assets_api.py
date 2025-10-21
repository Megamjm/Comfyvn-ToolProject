from __future__ import annotations

import json
import logging
import tempfile
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query,
                     UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.server.core.trash import move_to_trash
from comfyvn.server.modules.auth import require_scope
from comfyvn.studio.core import AssetRegistry

router = APIRouter(prefix="/assets", tags=["Assets"])

LOGGER = logging.getLogger(__name__)

_asset_registry = AssetRegistry()

MULTIPART_AVAILABLE = find_spec("multipart") is not None
if not MULTIPART_AVAILABLE:  # pragma: no cover - runtime branch
    LOGGER.warning(
        "python-multipart package is not installed; /assets/upload endpoint will return 503 until it is available.",
    )


def _parse_metadata(meta: Any) -> Dict[str, Any]:
    if meta in (None, "", b""):
        return {}
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, (bytes, bytearray)):
        meta = meta.decode("utf-8", errors="replace")
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except json.JSONDecodeError as exc:  # pragma: no cover - validation
            raise HTTPException(
                status_code=400, detail=f"metadata must be valid JSON: {exc}"
            ) from exc
    raise HTTPException(
        status_code=400, detail="metadata must be a JSON object or string."
    )


def _normalize_asset_payload(asset: Dict[str, Any]) -> Dict[str, Any]:
    meta = asset.get("meta")
    if isinstance(meta, str):
        try:
            asset["meta"] = json.loads(meta)
        except json.JSONDecodeError:
            asset["meta"] = {"raw": meta}
    elif meta is None:
        asset["meta"] = {}
    return asset


def _sanitize_relative_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(
            status_code=400, detail="dest_path must be relative to assets root."
        )
    return candidate


@router.get("/")
def list_assets(
    asset_type: Optional[str] = Query(
        None, alias="type", description="Optional asset type filter."
    ),
    limit: int = Query(200, ge=1, le=1000),
):
    """List assets stored in the registry."""
    assets = [
        _normalize_asset_payload(dict(item))
        for item in _asset_registry.list_assets(asset_type)
    ]
    return {"ok": True, "items": assets[:limit], "total": len(assets)}


@router.get("/{uid}")
def get_asset(uid: str):
    asset = _asset_registry.get_asset(uid)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return {"ok": True, "asset": _normalize_asset_payload(dict(asset))}


@router.get("/{uid}/download")
def download_asset(uid: str):
    asset = _asset_registry.get_asset(uid)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")
    path = _asset_registry.resolve_path(uid)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Asset file missing on disk.")
    return FileResponse(path, filename=path.name)


if MULTIPART_AVAILABLE:

    @router.post("/upload")
    async def upload_asset(
        file: UploadFile = File(...),
        asset_type: str = Form("generic", description="Logical asset type bucket."),
        dest_path: Optional[str] = Form(
            None, description="Optional relative destination path inside assets."
        ),
        metadata: Optional[str] = Form(
            None, description="JSON metadata to attach to the asset."
        ),
        _: bool = Depends(require_scope(["assets.write"])),
    ):
        """Upload a new asset and register it with sidecar + thumbnail support."""
        meta = _parse_metadata(metadata)
        dest_relative = _sanitize_relative_path(dest_path)

        suffix = Path(file.filename or "asset.bin").suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            data = await file.read()
            tmp.write(data)
            tmp_path = Path(tmp.name)

        if dest_relative and dest_relative.suffix:
            dest = dest_relative
        elif dest_relative:
            dest = dest_relative / (file.filename or tmp_path.name)
        else:
            dest = Path(asset_type) / (file.filename or tmp_path.name)
        try:
            provenance_payload = {
                "source": meta.get("source") or "api.upload",
                "inputs": {
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "size_bytes": len(data),
                },
                "user_id": meta.get("user_id"),
            }
            LOGGER.debug("Asset upload provenance payload: %s", provenance_payload)
            asset_info = _asset_registry.register_file(
                tmp_path,
                asset_type=asset_type,
                dest_relative=dest,
                metadata=meta,
                copy=True,
                provenance=provenance_payload,
                license_tag=meta.get("license"),
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        LOGGER.info("Asset uploaded uid=%s type=%s", asset_info["uid"], asset_type)
        return {"ok": True, "asset": asset_info}

else:

    @router.post("/upload")
    async def upload_asset_unavailable():
        LOGGER.error("Asset upload attempted but python-multipart is missing.")
        raise HTTPException(
            status_code=503,
            detail="Asset uploads require the python-multipart package to be installed on the server.",
        )

    upload_asset = upload_asset_unavailable


class RegisterAssetRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    path: str = Field(..., description="Absolute or relative path to the source file.")
    asset_type: str = Field("generic", description="Logical asset type bucket.")
    dest_path: Optional[str] = Field(
        None, description="Optional relative destination path inside assets."
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadata dictionary or JSON string."
    )
    copy_file: bool = Field(
        True,
        alias="copy",
        description="Copy the file into the assets directory (accepts legacy 'copy' JSON field).",
    )


@router.post("/register")
def register_existing_asset(
    payload: RegisterAssetRequest,
    _: bool = Depends(require_scope(["assets.write"])),
):
    """Register an existing file on disk into the asset registry."""
    source = Path(payload.path).expanduser()
    if not source.exists():
        raise HTTPException(status_code=404, detail="Source file does not exist.")

    asset_type = payload.asset_type or "generic"
    dest_relative = _sanitize_relative_path(payload.dest_path)
    if dest_relative and not dest_relative.suffix:
        dest_relative = dest_relative / source.name
    meta = _parse_metadata(payload.metadata)
    copy = payload.copy_file
    provenance_payload = {
        "source": meta.get("source") or "api.register_existing",
        "inputs": {
            "path": str(source),
            "copy": copy,
        },
        "user_id": meta.get("user_id"),
    }

    asset_info = _asset_registry.register_file(
        source,
        asset_type=asset_type,
        dest_relative=dest_relative,
        metadata=meta,
        copy=copy,
        provenance=provenance_payload,
        license_tag=meta.get("license"),
    )

    LOGGER.info("Registered existing asset uid=%s path=%s", asset_info["uid"], source)
    return {"ok": True, "asset": asset_info}


@router.delete("/{uid}")
def delete_asset(
    uid: str,
    remove_files: bool = Query(
        False, description="Physically remove files instead of moving to trash."
    ),
    _: bool = Depends(require_scope(["assets.write"])),
):
    """Delete an asset registry entry and optionally remove the underlying files."""
    asset = _asset_registry.get_asset(uid)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")

    if remove_files:
        _asset_registry.remove_asset(uid, delete_files=True)
        LOGGER.info("Removed asset uid=%s (files deleted)", uid)
        return {"ok": True, "removed": True}

    path = _asset_registry.resolve_path(uid)
    _asset_registry.remove_asset(uid, delete_files=False)
    if path and path.exists():
        move_to_trash(path)
    LOGGER.info("Trashed asset uid=%s", uid)
    return {"ok": True, "trashed": True}
