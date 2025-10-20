from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/modules/metrics_api.py
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
import os, time

try:
    from prometheus_client import generate_latest, REGISTRY
    _HAS_PROM = True
except Exception:
    _HAS_PROM = False

router = APIRouter()

@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
@router.get("/metrics/", response_class=PlainTextResponse, include_in_schema=False)
def metrics():
    if _HAS_PROM:
        try:
            data = generate_latest(REGISTRY)
            return PlainTextResponse(data, media_type="text/plain; version=0.0.4; charset=utf-8")
        except Exception:
            pass
    # Fallback minimal gauge so scrapers stay green
    body = (
        "# HELP comfyvn_up 1 means process responding\n"
        "# TYPE comfyvn_up gauge\n"
        "comfyvn_up 1\n"
    )
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")