from PySide6.QtGui import QAction

from fastapi import APIRouter, Header, HTTPException

router = APIRouter()

def _require_key(x_api_key: str | None, needed: str | None):
    if not needed:
        # security optional; pass
        return
    if not x_api_key or x_api_key != needed:
        raise HTTPException(status_code=401, detail="invalid or missing API key")

@router.get("/secure/ping")
def ping(x_api_key: str | None = Header(default=None)):
    # set COMFYVN_API_KEY in env to enforce
    needed = os.getenv("COMFYVN_API_KEY")
    _require_key(x_api_key, needed)
    return {"ok": True, "service": "secure", "auth": bool(needed)}

# avoid import cycle
import os