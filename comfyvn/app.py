from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter
# comfyvn/app.py
# ⚙️ ComfyVN Server Core — unified backend for GUI + embedded server
# [ComfyVN Architect | v0.6 Router Discovery + Stable Init]

import os, logging, importlib, pkgutil
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from comfyvn.logging_config import init_logging


# -------------------------------------------------------------------
# 🔧 Logging Initialization
# -------------------------------------------------------------------
LOG_PATH = init_logging(log_dir="logs", filename="server.log")
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# 🚀 Create FastAPI App
# -------------------------------------------------------------------
def create_app() -> FastAPI:
    """Factory that builds and configures the ComfyVN FastAPI app."""
    app = FastAPI(title="ComfyVN", version="0.6.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auto-discover and wire routers
    wired = _discover_and_include(app)
    logger.info(f"[Router Discovery] Wired routers: {wired}")

    return app


# -------------------------------------------------------------------
# 🔍 Auto-Discovery and Inclusion of Routers
# -------------------------------------------------------------------
def _discover_and_include(app: FastAPI):
    """Walk comfyvn.server.modules and include all APIRouter instances automatically."""
    wired = []
    base_mod = "comfyvn.server.modules"

    try:
        pkg = importlib.import_module(base_mod)
    except Exception as e:
        logger.warning(f"Failed to import {base_mod}: {e}")
        return wired

    for m in pkgutil.walk_packages(pkg.__path__, prefix=base_mod + "."):
        try:
            mod = importlib.import_module(m.name)
        except Exception as e:
            logger.debug(f"Failed to import module {m.name}: {e}")
            continue

        for name, obj in vars(mod).items():
            if isinstance(obj, APIRouter):
                try:
                    app.include_router(obj)
                    wired.append(f"{m.name}:{name}")
                except Exception as e:
                    logger.warning(f"Failed to include router {m.name}:{name}: {e}")

    return wired


# -------------------------------------------------------------------
# 🧩 Manual Fallback Router Includes (safety net)
# -------------------------------------------------------------------
def include_builtin_routers(app: FastAPI):
    """Explicitly include known routers (used if auto-discovery fails)."""
    for mod in (
        "comfyvn.server.modules.system_api",
        "comfyvn.server.modules.gpu_api",
        "comfyvn.server.modules.jobs_api",
        "comfyvn.server.modules.settings_api",
        "comfyvn.server.modules.snapshot_api",
        "comfyvn.server.modules.playground_api",
        "comfyvn.server.modules.roleplay.roleplay_api",
        "comfyvn.server.modules.events_api",
    ):
        try:
            m = importlib.import_module(mod)
            app.include_router(getattr(m, "router"))
            logger.info(f"[Manual Include] Loaded {mod}")
        except Exception as e:
            logger.warning(f"[Manual Include] Failed to load {mod}: {e}")


# -------------------------------------------------------------------
# 🩺 Health Endpoint (root)
# -------------------------------------------------------------------
app = FastAPI(title="ComfyVN Root", version="0.6.0")


@app.get("/healthz")
def healthz():
    return {"ok": True}


# -------------------------------------------------------------------
# 🏁 Entry Point
# -------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    host = os.getenv("COMFYVN_HOST", "127.0.0.1")
    port = int(os.getenv("COMFYVN_PORT", "8001"))

    logger.info(f"Starting ComfyVN backend on {host}:{port}")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")