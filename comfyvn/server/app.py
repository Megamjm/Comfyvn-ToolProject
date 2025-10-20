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
from typing import Iterable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from comfyvn.server.core.logging_ex import setup_logging

try:
    from fastapi.responses import ORJSONResponse as _ORJSON
except Exception:  # pragma: no cover - optional dependency
    _ORJSON = None

LOGGER = logging.getLogger(__name__)
APP_VERSION = os.getenv("COMFYVN_VERSION", "0.8.0")
MODULE_PACKAGE = "comfyvn.server.modules"
MODULE_PATH = Path(__file__).resolve().parent / "modules"
LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "server.log"


def _configure_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Preserve user override but ensure default path exists
    os.environ.setdefault("COMFYVN_LOG_FILE", str(LOG_PATH))
    setup_logging()
    LOGGER.info("Server logging configured -> %s", os.environ.get("COMFYVN_LOG_FILE"))


def _iter_module_names() -> Iterable[str]:
    for module_info in pkgutil.walk_packages([str(MODULE_PATH)], f"{MODULE_PACKAGE}."):
        if module_info.ispkg:
            continue
        yield module_info.name


def _include_routers(app: FastAPI) -> None:
    for module_name in _iter_module_names():
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            LOGGER.warning("Skipping router %s (import failed: %s)", module_name, exc)
            continue
        router = getattr(module, "router", None)
        if router is None:
            continue
        try:
            app.include_router(router)
            LOGGER.debug("Included router: %s", module_name)
        except Exception as exc:
            LOGGER.warning("Failed to include router %s: %s", module_name, exc)


def create_app(*, enable_cors: bool = True, allowed_origins: Optional[list[str]] = None) -> FastAPI:
    """Application factory used by both CLI launches and ASGI servers."""
    _configure_logging()

    default_kwargs = {"default_response_class": _ORJSON} if _ORJSON else {}
    app = FastAPI(title="ComfyVN", version=APP_VERSION, **default_kwargs)
    app.state.version = APP_VERSION

    if enable_cors:
        origins = allowed_origins or ["*"]
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

    @app.get("/status", tags=["System"], summary="Service status overview")
    async def core_status():
        routes = [
            route.path
            for route in app.routes
            if isinstance(route, APIRoute)
        ]
        return {"ok": True, "version": APP_VERSION, "routes": routes}

    LOGGER.info("FastAPI application created with %d routes", len(app.routes))
    return app


app = create_app()
