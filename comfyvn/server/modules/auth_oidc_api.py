from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse
import os, time, urllib.parse as _u

router = APIRouter()

def _cfg():
    issuer   = os.getenv("OIDC_ISSUER", "").strip()
    client   = os.getenv("OIDC_CLIENT_ID", "").strip()
    redirect = os.getenv("OIDC_REDIRECT_URL", "").strip()
    return {
        "issuer": issuer,
        "client_id": client,
        "redirect": redirect,
        "enabled": bool(issuer and client and redirect),
    }

@router.get("/oidc/health")
async def health():
    c = _cfg()
    return {"ok": True, "enabled": c["enabled"]}

@router.get("/oidc/config")
async def cfg():
    return _cfg()

@router.get("/oidc/login")
async def login():
    c = _cfg()
    if not c["enabled"]:
        return JSONResponse({"ok": False, "error": "oidc_not_configured"}, status_code=501)
    q = {
        "client_id": c["client_id"],
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": c["redirect"],
        "state": str(int(time.time())),
    }
    url = c["issuer"].rstrip("/") + "/authorize?" + _u.urlencode(q)
    return {"ok": True, "auth_url": url}

@router.get("/oidc/callback")
async def callback(request: Request):
    c = _cfg()
    if not c["enabled"]:
        return JSONResponse({"ok": False, "error": "oidc_not_configured"}, status_code=501)
    # Stub: echo received params; real token exchange omitted for dev mode
    qp = dict(request.query_params)
    return {"ok": True, "received": qp}