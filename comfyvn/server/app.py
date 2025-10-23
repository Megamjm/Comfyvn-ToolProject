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
import threading
import weakref
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence, Set, Tuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from comfyvn.config import ports as ports_config
from comfyvn.config.baseurl_authority import find_open_port
from comfyvn.core.warning_bus import warning_bus
from comfyvn.logging_config import init_logging
from comfyvn.obs.crash_reporter import install_sys_hook
from comfyvn.obs.telemetry import get_telemetry
from comfyvn.server.core.errors import register_exception_handlers
from comfyvn.server.core.event_stream import AsyncEventHub
from comfyvn.server.core.middleware_ex import RequestIDMiddleware, TimingMiddleware
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
    "comfyvn.server.modules.events_ws_api",
    "comfyvn.server.modules.gpu_api",
    "comfyvn.server.routes.audio",
    "comfyvn.server.routes.compute",
    "comfyvn.server.routes.providers",
    "comfyvn.server.routes.pov_worlds",
    "comfyvn.server.routes.diffmerge",
    "comfyvn.manga.routes",
)
BUILTIN_ROUTERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("comfyvn.server.routes.accessibility", ("router", "input_router")),
    ("comfyvn.server.routes.viewer", ("router",)),
    ("comfyvn.server.routes.pov", ("router",)),
    ("comfyvn.server.routes.llm", ("router",)),
    ("comfyvn.server.routes.pov_worlds", ("router",)),
    ("comfyvn.server.routes.perf", ("router",)),
    ("comfyvn.server.routes.themes", ("router",)),
    ("comfyvn.server.routes.weather", ("router",)),
    ("comfyvn.server.routes.battle", ("router",)),
    ("comfyvn.server.routes.providers_gpu", ("router",)),
    ("comfyvn.server.routes.providers_image_video", ("router",)),
    ("comfyvn.server.routes.providers_translate_ocr_speech", ("router",)),
    ("comfyvn.server.routes.providers_llm", ("router",)),
    ("comfyvn.server.routes.remote_orchestrator", ("router",)),
    ("comfyvn.server.routes.modder_hooks", ("router",)),
)

_LOGGED_BASE = False


if TYPE_CHECKING:
    from comfyvn.core.task_registry import TaskItem


class _TaskEventBridge:
    """Fan out task registry updates to all active event hubs."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._hubs: "weakref.WeakSet[AsyncEventHub]" = weakref.WeakSet()
        self._listener_registered = False
        self._registry = None
        self._registry_failed = False

    def register(self, hub: AsyncEventHub) -> None:
        with self._lock:
            self._hubs.add(hub)
            if not self._listener_registered:
                registry = self._get_registry()
                if registry is not None:
                    registry.subscribe(self._on_task_update)
                    self._listener_registered = True

    def unregister(self, hub: AsyncEventHub) -> None:
        with self._lock:
            self._hubs.discard(hub)

    def _on_task_update(self, task: Any) -> None:
        payload = _serialise_task(task)
        with self._lock:
            hubs = list(self._hubs)
        for hub in hubs:
            try:
                hub.publish("jobs.update", payload)
            except Exception:
                continue

    def _get_registry(self):
        if self._registry is None and not self._registry_failed:
            try:
                from comfyvn.core.task_registry import task_registry
            except Exception as exc:  # pragma: no cover - optional dependency
                LOGGER.debug("Task registry unavailable for event bridge: %s", exc)
                self._registry_failed = True
                return None
            self._registry = task_registry
        return self._registry


_TASK_EVENT_BRIDGE = _TaskEventBridge()


def _serialise_task(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "meta": task.meta,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


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
    host = str(port_config.get("host") or os.getenv("COMFYVN_HOST") or "127.0.0.1")
    candidates = _port_candidates(port_config)
    env_port = os.getenv("COMFYVN_PORT") or os.getenv("COMFYVN_SERVER_PORT")
    active_port: int | None = None
    if env_port:
        try:
            active_port = int(env_port)
        except (TypeError, ValueError):
            active_port = None
    if active_port is None:
        active_port = candidates[0]
    connect_host = _connect_host(host)
    if connect_host in {"127.0.0.1", "localhost"}:
        try:
            resolved = find_open_port(connect_host, active_port)
            if resolved != active_port:
                active_port = resolved
        except Exception:  # pragma: no cover - defensive fallback
            LOGGER.debug("find_open_port failed for %s:%s", connect_host, active_port)
    if active_port not in candidates:
        candidates.insert(0, active_port)
    elif candidates and candidates[0] != active_port:
        candidates = [active_port, *[p for p in candidates if p != active_port]]
    base_override = (
        os.getenv("COMFYVN_SERVER_BASE")
        or os.getenv("COMFYVN_BASE_URL")
        or os.getenv("COMFYVN_BASE")
    )
    public_base = port_config.get("public_base")
    if base_override:
        base_url = base_override.rstrip("/")
    elif public_base:
        base_url = str(public_base).rstrip("/")
    else:
        base_url = f"http://{connect_host}:{active_port}"
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


def _configure_logging() -> tuple[Path, str]:
    level = os.getenv("LOG_LEVEL") or os.getenv("COMFYVN_LOG_LEVEL", "INFO")
    log_dir_env = os.getenv("LOG_DIR")
    log_dir = Path(log_dir_env).expanduser() if log_dir_env else DEFAULT_LOG_PATH.parent
    log_path = init_logging(
        log_dir=log_dir,
        level=level,
        filename=DEFAULT_LOG_PATH.name,
    )
    warning_bus.attach_logging_handler()
    LOGGER.info(
        "Server logging configured",
        extra={"log_path": str(log_path), "log_level": level},
    )
    return log_path, level


def _include_router_module(
    app: FastAPI,
    module_name: str,
    *,
    seen: set[str],
    registry: Optional[list[str]] = None,
) -> None:
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
        if registry is not None:
            registry.append(module_name)
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


def _include_routers(
    app: FastAPI,
    *,
    seen: Optional[Set[str]] = None,
    registry: Optional[list[str]] = None,
) -> None:
    seen = set(seen or ())
    for module_name in PRIORITY_MODULES:
        _include_router_module(app, module_name, seen=seen, registry=registry)
    for module_name in _iter_module_names(MODULE_PATH, MODULE_PACKAGE):
        _include_router_module(app, module_name, seen=seen, registry=registry)
    for module_name in _iter_module_names(ROUTES_PATH, ROUTES_PACKAGE):
        _include_router_module(app, module_name, seen=seen, registry=registry)


def include_builtin_routers(app: FastAPI) -> tuple[list[str], Set[str]]:
    registry: list[str] = []
    seen: Set[str] = set()
    for module_name, attr_names in BUILTIN_ROUTERS:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            LOGGER.warning(
                "Skipping builtin router %s (import failed: %s)", module_name, exc
            )
            continue
        for attr_name in attr_names:
            router = getattr(module, attr_name, None)
            if router is None:
                continue
            router_routes = getattr(router, "routes", None)
            if not router_routes:
                continue
            existing_signatures = _collect_route_signatures(app.routes)
            router_signatures = _collect_route_signatures(router_routes)
            collisions = router_signatures.intersection(existing_signatures)
            if collisions:
                LOGGER.debug(
                    "Skipping builtin router %s.%s (collision %s)",
                    module_name,
                    attr_name,
                    ", ".join(sorted({path for path, _ in collisions})[:3]),
                )
                continue
            try:
                app.include_router(router)
                registry.append(f"{module_name}:{attr_name}")
            except Exception as exc:
                LOGGER.warning(
                    "Failed to include builtin router %s.%s: %s",
                    module_name,
                    attr_name,
                    exc,
                )
        seen.add(module_name)
    return registry, seen


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
    log_path, log_level = _configure_logging()

    port_config = ports_config.get_config()
    base_url, port_candidates, active_port, bind_host = _resolve_server_base(
        port_config
    )
    default_kwargs = {"default_response_class": _ORJSON} if _ORJSON else {}
    app = FastAPI(title="ComfyVN", version=APP_VERSION, **default_kwargs)
    app.state.version = APP_VERSION
    app.state.log_path = log_path
    app.state.log_level = log_level
    app.state.telemetry = get_telemetry(app_version=APP_VERSION)
    app.state.port_config = port_config
    app.state.port_candidates = port_candidates
    app.state.server_base = base_url
    app.state.bind_host = bind_host
    app.state.active_port = active_port
    app.state.router_catalog: list[str] = []

    global _LOGGED_BASE
    if not _LOGGED_BASE:
        LOGGER.info(
            "Server base configured",
            extra={
                "base_url": base_url,
                "bind_host": bind_host,
                "port_candidates": port_candidates,
            },
        )
        _LOGGED_BASE = True

    if enable_cors:
        origins = _resolve_cors_origins(allowed_origins)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        LOGGER.info("CORS enabled", extra={"origins": origins})

    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    event_hub = AsyncEventHub()
    app.state.event_hub = event_hub
    _TASK_EVENT_BRIDGE.register(event_hub)

    @app.on_event("shutdown")
    async def _on_shutdown() -> None:
        _TASK_EVENT_BRIDGE.unregister(event_hub)

    builtin_registry, preloaded_modules = include_builtin_routers(app)
    app.state.router_catalog.extend(builtin_registry)

    _include_routers(
        app, seen=set(preloaded_modules), registry=app.state.router_catalog
    )

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
            routes = sorted(
                {route.path for route in app.routes if isinstance(route, APIRoute)}
            )
            return {
                "ok": True,
                "version": APP_VERSION,
                "routes": routes,
                "routers": list(app.state.router_catalog),
                "base_url": app.state.server_base,
                "log_path": str(app.state.log_path),
            }

    if not _route_exists(app, "/system/metrics", {"GET"}):

        @app.get(
            "/system/metrics",
            tags=["System"],
            summary="System metrics snapshot",
        )
        async def core_metrics():
            return collect_system_metrics()

    LOGGER.info(
        "FastAPI application ready",
        extra={
            "routes": len(app.routes),
            "routers_loaded": len(app.state.router_catalog),
            "version": APP_VERSION,
        },
    )
    return app


if os.getenv("COMFYVN_SKIP_APP_AUTOLOAD", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}:
    app: FastAPI | None = None
else:
    app = create_app()
