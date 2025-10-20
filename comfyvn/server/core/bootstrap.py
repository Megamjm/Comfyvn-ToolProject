from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/server/core/bootstrap.py
# 🧱 ComfyVN Server Bootstrap — builds FastAPI app, managers, and routers (v4.0)
# [ComfyVN Architect | Modular Server Core]

import os, json, time, asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from comfyvn.server.core.import_utils import safe_import
from comfyvn.server.core.diagnostics import log_diagnostic, dump_startup_report
from comfyvn.server.core.manager_loader import load_managers
from comfyvn.server.core.router_loader import load_routers
from comfyvn.server.core.ws_handlers import register_ws_endpoints


def create_app() -> FastAPI:
    app = FastAPI(title="ComfyVN", version="4.0-dev")

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Load managers ---
    state = load_managers()
    for key, val in state.items():
        setattr(app.state, key, val)
    log_diagnostic("Managers", list(state.keys()))

    # --- Include routers ---
    loaded, failed = load_routers(app)
    log_diagnostic("Routers", {"loaded": loaded, "failed": failed})

    # --- WebSocket + SSE subsystems ---
    register_ws_endpoints(app)

    # --- Base routes ---
    @app.get("/")
    async def root():
        return {
            "ok": True,
            "version": app.version,
            "managers": list(state.keys()),
            "routers": loaded,
        }

    @app.exception_handler(404)
    async def not_found(_, __):
        return PlainTextResponse("Not Found", status_code=404)

    dump_startup_report()
    port = os.environ.get("COMFYVN_SERVER_PORT", "8001")
    print(f"[ComfyVN] ✅ Server started on port {port}")
    return app
