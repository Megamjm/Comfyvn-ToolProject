from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute

from comfyvn.plugins.loader import (
    PluginDefinition,
    PluginLoader,
    PluginManifestError,
    RouteContribution,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["Extensions"])
_loader = PluginLoader()
_mounted_routes: Dict[str, List[APIRoute]] = {}
_initialised: bool = False


def _serialize_plugin(plugin: PluginDefinition) -> Dict[str, Any]:
    routes = [
        {
            "path": route.path,
            "methods": route.methods,
            "expose": route.expose,
            "name": route.name,
            "summary": route.summary,
            "status_code": route.status_code,
            "tags": route.tags,
        }
        for route in plugin.routes
    ]
    panels = [
        {
            "slot": panel.slot,
            "label": panel.label,
            "path": panel.path,
            "icon": panel.icon,
            "plugin_id": panel.plugin_id,
        }
        for panel in plugin.panels
    ]
    return {
        "id": plugin.id,
        "name": plugin.name,
        "version": plugin.version,
        "description": plugin.description,
        "summary": plugin.summary,
        "trust": plugin.trust_level,
        "permissions": plugin.permissions,
        "hooks": plugin.hooks,
        "enabled": plugin.enabled,
        "enabled_by_default": plugin.enabled_by_default,
        "errors": plugin.errors,
        "warnings": plugin.warnings,
        "routes": routes,
        "panels": panels,
    }


def _iter_enabled_routes() -> Iterable[tuple[PluginDefinition, RouteContribution]]:
    for plugin in _loader.enabled_plugins():
        for route in plugin.routes:
            yield plugin, route


def _resolve_route_path(plugin_id: str, route: RouteContribution) -> str:
    if route.path.startswith("/"):
        raw_path = route.path
    else:
        raw_path = f"/{route.path}"
    if route.expose == "global":
        return raw_path
    base = f"/api/extensions/{plugin_id}"
    if raw_path == "/":
        return base
    return f"{base}{raw_path}"


def _clear_mounted_routes() -> None:
    for routes in _mounted_routes.values():
        for route in routes:
            try:
                router.routes.remove(route)
            except ValueError:
                continue
    _mounted_routes.clear()


def _mount_routes() -> None:
    _clear_mounted_routes()
    for plugin, contribution in _iter_enabled_routes():
        full_path = _resolve_route_path(plugin.id, contribution)
        try:
            mounted = router.add_api_route(
                full_path,
                contribution.handler,
                methods=contribution.methods,
                name=contribution.name
                or f"{plugin.id}:{contribution.handler.__name__}",
                summary=contribution.summary,
                status_code=contribution.status_code,
                tags=contribution.tags,
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning(
                "Failed mounting route %s for plugin %s: %s",
                full_path,
                plugin.id,
                exc,
            )
            continue
        _mounted_routes.setdefault(plugin.id, []).append(mounted)


def _ensure_loaded() -> None:
    global _initialised
    if _initialised:
        return
    _loader.refresh()
    _mount_routes()
    _initialised = True


@router.on_event("startup")
async def _startup() -> None:
    global _initialised
    _loader.refresh()
    _mount_routes()
    _initialised = True


@router.get("/api/extensions")
def list_extensions() -> Dict[str, Any]:
    _ensure_loaded()
    return {"ok": True, "items": [_serialize_plugin(p) for p in _loader.list_plugins()]}


@router.post("/api/extensions/{plugin_id}/enable")
def enable_extension(plugin_id: str) -> Dict[str, Any]:
    _ensure_loaded()
    try:
        plugin = _loader.enable(plugin_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"plugin '{plugin_id}' not found"
        ) from exc
    except PluginManifestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _mount_routes()
    return {"ok": True, "plugin": _serialize_plugin(plugin)}


@router.post("/api/extensions/{plugin_id}/disable")
def disable_extension(plugin_id: str) -> Dict[str, Any]:
    _ensure_loaded()
    try:
        plugin = _loader.disable(plugin_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"plugin '{plugin_id}' not found"
        ) from exc
    _mount_routes()
    return {"ok": True, "plugin": _serialize_plugin(plugin)}


@router.post("/api/extensions/reload")
def reload_extensions() -> Dict[str, Any]:
    _ensure_loaded()
    _loader.refresh()
    _mount_routes()
    return {"ok": True, "items": [_serialize_plugin(p) for p in _loader.list_plugins()]}


@router.get("/api/extensions/ui/panels")
def list_ui_panels() -> Dict[str, Any]:
    _ensure_loaded()
    panels = [
        {
            "plugin_id": panel.plugin_id,
            "slot": panel.slot,
            "label": panel.label,
            "path": panel.path,
            "icon": panel.icon,
        }
        for panel in _loader.panels_for_enabled()
    ]
    return {"ok": True, "panels": panels}


@router.get("/api/extensions/{plugin_id}/ui/{asset_path:path}")
def fetch_ui_asset(plugin_id: str, asset_path: str) -> FileResponse:
    _ensure_loaded()
    try:
        resolved = _loader.resolve_panel_asset(plugin_id, asset_path)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"plugin '{plugin_id}' not found"
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"asset '{asset_path}' not found"
        ) from exc
    return FileResponse(resolved)
