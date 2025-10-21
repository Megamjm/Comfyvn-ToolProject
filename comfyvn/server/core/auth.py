from __future__ import annotations

import os

# comfyvn/server/core/auth.py
from fastapi import Header, HTTPException
from PySide6.QtGui import QAction


def api_key_auth(
    x_api_key: str | None = Header(default=None, alias="x-api-key")
) -> bool:
    expected = os.getenv("COMFYVN_API_KEY")
    if not expected:
        return True
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid API key")
    return True
