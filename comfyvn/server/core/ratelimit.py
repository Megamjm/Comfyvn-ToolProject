from __future__ import annotations
from PySide6.QtGui import QAction
import time
from fastapi import HTTPException

class RateLimitError(HTTPException):
    def __init__(self, detail: str = "rate limit exceeded"):
        super().__init__(status_code=429, detail=detail)

def enforce(db, token_row, cost: int = 1):
    now = time.time()
    # Defaults if columns are absent
    def g(name, d=0): 
        try: return int(getattr(token_row, name))
        except Exception: return d
    def s(name, v):
        try: setattr(token_row, name, v)
        except Exception: pass
    # windows
    if now - float(getattr(token_row, "window_min", 0.0) or 0.0) >= 60.0:
        s("window_min", now); s("used_min", 0)
    if now - float(getattr(token_row, "window_day", 0.0) or 0.0) >= 86400.0:
        s("window_day", now); s("used_day", 0)

    if g("limit_per_min") and g("used_min")+cost > g("limit_per_min"): raise RateLimitError("minute limit exceeded")
    if g("limit_per_day") and g("used_day")+cost > g("limit_per_day"): raise RateLimitError("daily limit exceeded")
    if g("quota_total") and g("used_total")+cost > g("quota_total"): raise RateLimitError("quota exceeded")

    s("used_min", g("used_min")+cost); s("used_day", g("used_day")+cost); s("used_total", g("used_total")+cost)
    try: db.commit()
    except Exception: pass