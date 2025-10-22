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
from typing import Any, Iterable, Optional, Sequence, Set, Tuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from comfyvn.config import ports as ports_config
from comfyvn.core.warning_bus import warning_bus
from comfyvn.logging_config import init_logging
from comfyvn.obs.crash_reporter import install_sys_hook
from comfyvn.obs.telemetry import get_telemetry
from comfyvn.server.routes import accessibility as accessibility_routes
from comfyvn.server.routes import battle as battle_routes
from comfyvn.server.routes import llm as llm_routes
from comfyvn.server.routes import (
    modder_hooks,
    pov_worlds,
    providers_gpu,
    providers_image_video,
    providers_llm,
    providers_translate_ocr_speech,
    remote_orchestrator,
)
from comfyvn.server.routes import perf as perf_routes
from comfyvn.server.routes import pov as pov_routes
from comfyvn.server.routes import themes as themes_routes
from comfyvn.server.routes import viewer as viewer_routes
from comfyvn.server.routes import weather as weather_routes
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
ROUTES_PACKAGE = "comfyvn.server.routes"
ROUTES_PATH = Path(__file__).resolve().parent / "routes"
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
    "comfyvn.server.routes.audio",
    "comfyvn.server.routes.compute",
    "comfyvn.server.routes.providers",
    "comfyvn.server.routes.pov_worlds",
    "comfyvn.server.routes.diffmerge",
    "comfyvn.manga.routes",
)

_LOGGED_BASE = False


def _connect_host(host: str) -> str:
    lowered = host.strip().lower()
    if lowered in {"0.0.0.0", "0", "*"}:
        return "127.0.0.1"
    if lowered in {"::", "[::]", "::0"}:
        return "localhost"
    return host


def _port_candidates(port_config: dict[str, object]) -> list[int]:
    ports = port_config.get("ports") or []
    numbers: list[int] = []
    for raw in ports if isinstance(ports, (list, tuple)) else [ports]:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value not in numbers:
            numbers.append(value)
    if not numbers:
        numbers = [8001, 8000]
    return numbers


def _resolve_server_base(
    port_config: dict[str, object]
) -> tuple[str, list[int], int, str]:
    host = str(port_config.get("host") or "127.0.0.1")
    candidates = _port_candidates(port_config)
    env_port = os.getenv("COMFYVN_SERVER_PORT")
    active_port: int | None = None
    if env_port:
        try:
            active_port = int(env_port)
        except (TypeError, ValueError):
            active_port = None
    if active_port is None:
        active_port = candidates[0]
    base_override = os.getenv("COMFYVN_SERVER_BASE") or os.getenv("COMFYVN_BASE_URL")
    public_base = port_config.get("public_base")
    if base_override:
        base_url = base_override.rstrip("/")
    elif public_base:
        base_url = str(public_base).rstrip("/")
    else:
        base_url = f"http://{_connect_host(host)}:{active_port}"
    return base_url, candidates, active_port, host


def _collect_route_signatures(routes: Iterable[Any]) -> Set[Tuple[str, str]]:
    signatures: Set[Tuple[str, str]] = set()
    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            signatures.add((route.path, method))
    return signatures


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
    router_routes = getattr(router, "routes", None)
    if not router_routes:
        return
    existing_signatures = _collect_route_signatures(app.routes)
    router_signatures = _collect_route_signatures(router_routes)
    collisions = router_signatures.intersection(existing_signatures)
    if collisions:
        LOGGER.debug(
            "Skipping router %s (route collision on %s)",
            module_name,
            ", ".join(sorted({path for path, _ in collisions})[:3]),
        )
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


def _iter_module_names(
    base_path: Path = MODULE_PATH, package: str = MODULE_PACKAGE
) -> Iterable[str]:
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

    yield from _walk([str(base_path)], f"{package}.")


def _include_routers(app: FastAPI, *, seen: Optional[Set[str]] = None) -> None:
    seen = set(seen or ())
    for module_name in PRIORITY_MODULES:
        _include_router_module(app, module_name, seen=seen)
    for module_name in _iter_module_names(MODULE_PATH, MODULE_PACKAGE):
        _include_router_module(app, module_name, seen=seen)
    for module_name in _iter_module_names(ROUTES_PATH, ROUTES_PACKAGE):
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
    install_sys_hook()
    log_path = _configure_logging()

    port_config = ports_config.get_config()
    base_url, port_candidates, active_port, bind_host = _resolve_server_base(
        port_config
    )
    public_base_value = port_config.get("public_base")
    default_kwargs = {"default_response_class": _ORJSON} if _ORJSON else {}
    app = FastAPI(title="ComfyVN", version=APP_VERSION, **default_kwargs)
    app.state.version = APP_VERSION
    app.state.log_path = log_path
    app.state.telemetry = get_telemetry(app_version=APP_VERSION)
    app.state.port_config = port_config
    app.state.port_candidates = port_candidates
    app.state.server_base = base_url
    app.state.bind_host = bind_host

    global _LOGGED_BASE
    if not _LOGGED_BASE:
        LOGGER.info(
            "Server base configured -> %s (host=%s, ports=%s)",
            base_url,
            bind_host,
            port_candidates,
        )
        _LOGGED_BASE = True

    ports_config.record_runtime_state(
        host=bind_host,
        ports=port_candidates,
        active_port=active_port,
        base_url=base_url,
        public_base=str(public_base_value) if public_base_value else None,
    )

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

    preloaded_modules: Set[str] = {
        accessibility_routes.__name__,
        viewer_routes.__name__,
        pov_routes.__name__,
        llm_routes.__name__,
        pov_worlds.__name__,
        perf_routes.__name__,
        themes_routes.__name__,
        weather_routes.__name__,
        battle_routes.__name__,
        providers_gpu.__name__,
        providers_image_video.__name__,
        providers_translate_ocr_speech.__name__,
        providers_llm.__name__,
        remote_orchestrator.__name__,
        modder_hooks.__name__,
    }
    app.include_router(accessibility_routes.router)
    app.include_router(accessibility_routes.input_router)
    app.include_router(viewer_routes.router)
    app.include_router(pov_routes.router)
    app.include_router(llm_routes.router)
    app.include_router(pov_worlds.router)
    app.include_router(perf_routes.router)
    app.include_router(themes_routes.router)
    app.include_router(weather_routes.router)
    app.include_router(battle_routes.router)
    app.include_router(providers_gpu.router)
    app.include_router(providers_image_video.router)
    app.include_router(providers_translate_ocr_speech.router)
    app.include_router(providers_llm.router)
    app.include_router(remote_orchestrator.router)
    app.include_router(modder_hooks.router)

    _include_routers(app, seen=preloaded_modules)

    if not _route_exists(app, "/health", {"GET"}):

        @app.get("/health", tags=["System"], summary="Simple health probe")
        async def core_health():
            return {"status": "ok"}

    @app.get("/healthz", include_in_schema=False)
    async def _healthz():
        return {"ok": True}

    if not _route_exists(app, "/status", {"GET"}):

        @app.get("/status", tags=["System"], summary="Service status overview")
        async def core_status():
            routes = [route.path for route in app.routes if isinstance(route, APIRoute)]
            return {
                "status": "ok",
                "ok": True,
                "version": APP_VERSION,
                "routes": routes,
            }

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
