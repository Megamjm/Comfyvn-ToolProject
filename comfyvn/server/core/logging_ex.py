from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/core/logging_ex.py
import logging, os, sys, json
from logging.handlers import RotatingFileHandler
from typing import Optional

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "lvl": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.__dict__.get("extra"):
            payload["extra"] = record.__dict__["extra"]
        return json.dumps(payload, ensure_ascii=False)

def _mk_handler(to_file: Optional[str], level: int) -> logging.Handler:
    fmt = JsonFormatter()
    if to_file:
        os.makedirs(os.path.dirname(to_file) or ".", exist_ok=True)
        h = RotatingFileHandler(to_file, maxBytes=int(os.getenv("COMFYVN_LOG_MAXBYTES", "10485760")), backupCount=int(os.getenv("COMFYVN_LOG_BACKUPS", "5")))
    else:
        h = logging.StreamHandler(sys.stdout)
    h.setLevel(level)
    h.setFormatter(fmt)
    return h

def setup_logging() -> None:
    level_name = os.getenv("COMFYVN_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    to_file = os.getenv("COMFYVN_LOG_FILE") or None

    root = logging.getLogger()
    # clear existing handlers once
    root.handlers[:] = []
    root.setLevel(level)
    root.addHandler(_mk_handler(to_file, level))

    # quiet noisy deps
    for noisy in ("uvicorn.access", "watchfiles.main"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))