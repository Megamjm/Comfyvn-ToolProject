from __future__ import annotations

"""Legacy entrypoint that re-exports the main server application factory."""

import logging
import os

from comfyvn.server.app import app as app
from comfyvn.server.app import create_app as create_app

__all__ = ["create_app", "app"]

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("COMFYVN_HOST", "127.0.0.1")
    port = int(os.getenv("COMFYVN_PORT", "8001"))
    log_level = os.getenv("COMFYVN_UVICORN_LOG_LEVEL", "info")

    logger.info("Starting ComfyVN backend on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level=log_level)
