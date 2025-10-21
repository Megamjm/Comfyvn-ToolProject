"""
ComfyVN FastAPI entrypoint.

Provides a ``create_app`` factory that configures logging, CORS, core routes,
and dynamically loads all available API routers under ``comfyvn.server.modules``.
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from pathlib import Path
from typing import Iterable, Optional, Sequence, Set

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from comfyvn.core.warning_bus import warning_bus
from comfyvn.logging_config import init_logging
from comfyvn.server.system_metrics import collect_system_metrics

try:
    import orjson as _orjson  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    _orjson = None

try:
    from fastapi.responses import ORJSONResponse as _ORJSON
except Exception:  # pragma: no cover - optional dependency
    _ORJSON = None

if _ORJSON is not None and _orjson is None:
    _ORJSON = None

LOGGER = logging.getLogger(__name__)
APP_VERSION = os.getenv("COMFYVN_VERSION", "0.8.0")
MODULE_PACKAGE = "comfyvn.server.modules"
MODULE_PATH = Path(__file__).resolve().parent / "modules"
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)
DEFAULT_LOG_PATH = Path("./logs/server.log").resolve()
PRIORITY_MODULES: tuple[str, ...] = (
    "comfyvn.server.modules.system_api",
    "comfyvn.server.modules.settings_api",
    "comfyvn.server.modules.jobs_api",
    "comfyvn.server.modules.roleplay_api",
    "comfyvn.server.modules.playground_api",
    "comfyvn.server.modules.events_api",
    "comfyvn.server.modules.gpu_api",
)


def _configure_logging() -> Path:
    level = os.getenv("COMFYVN_LOG_LEVEL", "INFO")
    DEFAULT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_path = init_logging(
        log_dir=DEFAULT_LOG_PATH.parent,
        level=level,
        filename=DEFAULT_LOG_PATH.name,
    )
    warning_bus.attach_logging_handler()
    LOGGER.info("Server logging configured -> %s", log_path)
    return log_path


def _iter_module_names() -> Iterable[str]:
    def _walk(paths: list[str], prefix: str) -> Iterable[str]:
        for module_info in pkgutil.iter_modules(paths, prefix):
            name = module_info.name
            if module_info.ispkg:
                sub_paths: list[str] = []
                finder = getattr(module_info, "module_finder", None)
                find_spec = getattr(finder, "find_spec", None)
                if find_spec is not None:
                    try:
                        spec = find_spec(name)
                    except Exception:  # pragma: no cover - defensive
                        spec = None
                    if spec and spec.submodule_search_locations:
                        sub_paths = list(spec.submodule_search_locations)
                if sub_paths:
                    yield from _walk(sub_paths, f"{name}.")
                continue
            yield name

    yield from _walk([str(MODULE_PATH)], f"{MODULE_PACKAGE}.")


def _include_router_module(app: FastAPI, module_name: str, *, seen: set[str]) -> None:
    if module_name in seen:
        return
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        LOGGER.warning("Skipping router %s (import failed: %s)", module_name, exc)
        return
    router = getattr(module, "router", None)
    if router is None:
        return
    try:
        app.include_router(router)
        seen.add(module_name)
        LOGGER.debug(
            "Included router: %s (prefix=%s)",
            module_name,
            getattr(router, "prefix", ""),
        )
    except Exception as exc:
        LOGGER.warning("Failed to include router %s: %s", module_name, exc)


def _include_routers(app: FastAPI) -> None:
    seen: set[str] = set()
    for module_name in PRIORITY_MODULES:
        _include_router_module(app, module_name, seen=seen)
    for module_name in _iter_module_names():
        _include_router_module(app, module_name, seen=seen)


def _route_exists(app: FastAPI, path: str, methods: Set[str]) -> bool:
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path != path:
            continue
        route_methods = getattr(route, "methods", None) or set()
        if route_methods.intersection(methods):
            return True
    return False


def _resolve_cors_origins(allowed_origins: Optional[Sequence[str]]) -> list[str]:
    if allowed_origins is not None:
        origins = list(allowed_origins)
    else:
        origins = list(DEFAULT_ALLOWED_ORIGINS)
    extra = os.getenv("COMFYVN_CORS_ORIGINS", "")
    if extra:
        origins.extend(origin.strip() for origin in extra.split(",") if origin.strip())
    # Preserve order while removing duplicates
    return list(dict.fromkeys(origins))


def create_app(
    *, enable_cors: bool = True, allowed_origins: Optional[Sequence[str]] = None
) -> FastAPI:
    """Application factory used by both CLI launches and ASGI servers."""
    log_path = _configure_logging()

    default_kwargs = {"default_response_class": _ORJSON} if _ORJSON else {}
    app = FastAPI(title="ComfyVN", version=APP_VERSION, **default_kwargs)
    app.state.version = APP_VERSION
    app.state.log_path = log_path

    if enable_cors:
        origins = _resolve_cors_origins(allowed_origins)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        LOGGER.info("CORS enabled for origins: %s", origins)

    _include_routers(app)

    @app.get("/health", tags=["System"], summary="Simple health probe")
    async def core_health():
        return {"status": "ok"}

    @app.get("/healthz", include_in_schema=False)
    async def _healthz():
        return {"ok": True}

    @app.get("/status", tags=["System"], summary="Service status overview")
    async def core_status():
        routes = [route.path for route in app.routes if isinstance(route, APIRoute)]
        return {"status": "ok", "ok": True, "version": APP_VERSION, "routes": routes}

    if not _route_exists(app, "/system/metrics", {"GET"}):

        @app.get(
            "/system/metrics",
            tags=["System"],
            summary="System metrics snapshot",
        )
        async def core_metrics():
            return collect_system_metrics()

    LOGGER.info("FastAPI application created with %d routes", len(app.routes))
    return app


app = create_app()
