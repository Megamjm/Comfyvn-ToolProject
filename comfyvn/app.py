from __future__ import annotations

import logging
import os
from typing import Optional, Sequence

from fastapi import FastAPI
from fastapi.routing import APIRoute

from comfyvn.server.app import create_app as _create_app

logger = logging.getLogger(__name__)
__all__ = ["create_app", "app"]


def _ensure_legacy_health(app: FastAPI) -> None:
    """Attach the legacy /healthz route for older tooling if it is missing."""
    if any(isinstance(route, APIRoute) and route.path == "/healthz" for route in app.routes):
        return

    @app.get("/healthz", tags=["System"], summary="Legacy health probe")
    async def _healthz() -> dict[str, bool]:
        return {"ok": True}


def create_app(
    *, enable_cors: bool = True, allowed_origins: Optional[Sequence[str]] = None
) -> FastAPI:
    """
    Build the FastAPI application using the canonical server factory and
    ensure compatibility endpoints remain available.
    """
    logger.debug("Delegating create_app to comfyvn.server.app (enable_cors=%s)", enable_cors)
    cors_origins = list(allowed_origins) if allowed_origins is not None else None
    app = _create_app(enable_cors=enable_cors, allowed_origins=cors_origins)
    _ensure_legacy_health(app)
    log_path = getattr(app.state, "log_path", None)
    if log_path:
        logger.debug("Server logging rooted at %s", log_path)
    logger.debug("FastAPI app ready (routes=%d)", len(app.routes))
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("COMFYVN_HOST", "127.0.0.1")
    port = int(os.getenv("COMFYVN_PORT", "8001"))
    log_level = os.getenv("COMFYVN_UVICORN_LOG_LEVEL", "info")

    logger.info("Starting ComfyVN backend on %s:%s", host, port)
    uvicorn.run(create_app(), host=host, port=port, log_level=log_level)
