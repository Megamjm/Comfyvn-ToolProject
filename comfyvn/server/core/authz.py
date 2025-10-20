from __future__ import annotations
from PySide6.QtGui import QAction
import os
from fastapi import Header, HTTPException

_API_KEY = os.getenv("API_KEY", "").strip()

async def require_api_key(x_api_key: str | None = Header(default=None)):
    if not _API_KEY:
        return True  # auth disabled
    if x_api_key == _API_KEY:
        return True
    raise HTTPException(401, "unauthorized")