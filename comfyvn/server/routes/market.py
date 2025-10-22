from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping

from fastapi import APIRouter, Body, HTTPException

from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.market import ExtensionMarket, ManifestError, validate_manifest_payload
from comfyvn.market.manifest import KNOWN_PERMISSION_SCOPES, TRUST_LEVELS

try:  # Ensure the server includes this router before legacy modules.
    from comfyvn.server import app as server_app

    if "comfyvn.server.routes.market" not in server_app.PRIORITY_MODULES:
        server_app.PRIORITY_MODULES = ("comfyvn.server.routes.market",) + tuple(
            module
            for module in server_app.PRIORITY_MODULES
            if module != "comfyvn.server.routes.market"
        )
except Exception:  # pragma: no cover - optional import during tooling/tests
    pass

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["Marketplace"])
_market = ExtensionMarket()
_LAST_ERROR: Dict[str, Any] | None = None


def _load_flag(name: str) -> bool | None:
    flags = feature_flags.load_feature_flags()
    if name in flags:
        return bool(flags[name])
    return None


def _is_marketplace_enabled() -> bool:
    enabled = _load_flag("enable_marketplace")
    if enabled is not None:
        return enabled
    legacy = _load_flag("enable_extension_market")
    return bool(legacy)


def _ensure_enabled(operation: str | None = None) -> None:
    if not _is_marketplace_enabled():
        detail = "extension marketplace disabled"
        if operation:
            detail = f"{detail} for {operation}"
        raise HTTPException(status_code=403, detail=detail)


def _record_error(
    action: str, message: str, *, context: Mapping[str, Any] | None = None
) -> None:
    global _LAST_ERROR
    payload: Dict[str, Any] = {
        "action": action,
        "message": message,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if context:
        payload["context"] = dict(context)
    _LAST_ERROR = payload


def _clear_error() -> None:
    global _LAST_ERROR
    _LAST_ERROR = None


def _summarise_manifest(
    manifest_payload: Mapping[str, Any] | Any
) -> Dict[str, Any] | None:
    if not isinstance(manifest_payload, Mapping):
        return None
    trust_payload = manifest_payload.get("trust")
    trust_level = None
    if isinstance(trust_payload, Mapping):
        trust_level = trust_payload.get("level")
    try:
        manifest = validate_manifest_payload(
            manifest_payload,
            trust_level=str(trust_level) if trust_level else None,
        )
    except ManifestError:
        return None
    capabilities = manifest.contribution_summary()
    return {
        "id": manifest.id,
        "name": manifest.name,
        "version": manifest.version,
        "summary": manifest.summary,
        "authors": manifest.authors,
        "primary_author": manifest.primary_author(),
        "trust": manifest.trust.model_dump(exclude_none=True),
        "capabilities": capabilities,
    }


def _available_modder_hooks() -> Iterable[Dict[str, Any]]:
    specs = modder_hooks.hook_specs()
    for name in sorted(specs):
        spec = specs[name]
        yield {
            "name": spec.name,
            "description": spec.description,
            "payload": spec.payload_fields,
            "ws_topic": spec.ws_topic,
            "rest_event": spec.rest_event,
        }


@router.get("/list")
def list_market() -> Dict[str, Any]:
    _ensure_enabled("list")
    catalog_items = []
    for entry in _market.catalog.entries():
        payload = entry.to_payload()
        payload.pop("manifest", None)  # Manifest objects are not JSON serialisable.
        manifest = entry.manifest
        if manifest:
            manifest_payload = manifest.to_loader_payload()
            summary = _summarise_manifest(manifest_payload)
            if summary:
                payload.update(
                    {
                        "summary": summary["summary"],
                        "authors": summary["authors"] or payload.get("authors", []),
                        "primary_author": summary["primary_author"],
                        "capabilities": summary["capabilities"],
                        "manifest_summary": summary,
                        "diagnostics": manifest.diagnostics.model_dump(),
                    }
                )
        else:
            payload.setdefault("capabilities", {})
            payload.setdefault("authors", [])
            payload["primary_author"] = (
                payload["authors"][0] if payload["authors"] else None
            )
        catalog_items.append(payload)

    installed_items = []
    for item in _market.list_installed():
        entry = dict(item)
        manifest_payload = entry.get("manifest")
        if isinstance(manifest_payload, Mapping):
            summary = _summarise_manifest(manifest_payload)
            if summary:
                entry["manifest_summary"] = summary
                entry["capabilities"] = summary["capabilities"]
                entry["diagnostics"] = summary["capabilities"].get("diagnostics", {})
                entry.setdefault("name", summary["name"])
                entry.setdefault("version", summary["version"])
                entry.setdefault("summary", summary["summary"])
                entry.setdefault("authors", summary["authors"])
        installed_items.append(entry)

    permissions_catalog = [
        {"scope": scope, "description": KNOWN_PERMISSION_SCOPES[scope]}
        for scope in sorted(KNOWN_PERMISSION_SCOPES)
    ]
    return {
        "ok": True,
        "catalog": catalog_items,
        "installed": installed_items,
        "hooks": list(_available_modder_hooks()),
        "permissions": permissions_catalog,
        "trust_levels": list(TRUST_LEVELS),
    }


@router.post("/install")
def install(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _ensure_enabled("install")
    package = str(payload.get("package") or payload.get("package_path") or "").strip()
    if not package:
        raise HTTPException(status_code=400, detail="package path is required")
    trust_override = payload.get("trust")
    if trust_override is not None:
        trust_override = str(trust_override)
    try:
        result = _market.install(package, trust_override=trust_override)
    except ManifestError as exc:
        _record_error("install", str(exc), context={"package": package})
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _clear_error()
    installed_payload = result.to_payload()
    summary = _summarise_manifest(installed_payload.get("manifest", {}))
    if summary:
        installed_payload["manifest_summary"] = summary
        installed_payload["capabilities"] = summary["capabilities"]
        installed_payload["diagnostics"] = summary["capabilities"].get(
            "diagnostics", {}
        )
    LOGGER.info(
        "market.install",
        extra={
            "event": "market.install",
            "extension_id": result.extension_id,
            "trust": result.trust.level,
            "package": str(result.package_path),
            "sha256": result.package_sha256,
        },
    )
    return {"ok": True, "installed": installed_payload}


@router.post("/uninstall")
def uninstall(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _ensure_enabled("uninstall")
    extension_id = str(
        payload.get("id")
        or payload.get("extension_id")
        or payload.get("plugin_id")
        or ""
    ).strip()
    if not extension_id:
        raise HTTPException(status_code=400, detail="extension id is required")
    try:
        _market.uninstall(extension_id)
    except ManifestError as exc:
        _record_error("uninstall", str(exc), context={"extension_id": extension_id})
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _clear_error()
    LOGGER.info(
        "market.uninstall",
        extra={
            "event": "market.uninstall",
            "extension_id": extension_id,
        },
    )
    return {"ok": True, "id": extension_id}


@router.get("/health")
def health() -> Dict[str, Any]:
    _ensure_enabled("health")
    installed = _market.list_installed()
    counts: Dict[str, int] = {}
    for entry in installed:
        trust_payload = entry.get("trust") or {}
        level = str(trust_payload.get("level") or "unverified").lower()
        counts[level] = counts.get(level, 0) + 1
    return {
        "ok": True,
        "catalog_count": len(_market.catalog.entries()),
        "installed_count": len(installed),
        "trust_breakdown": counts,
        "last_error": _LAST_ERROR,
    }
