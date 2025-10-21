from __future__ import annotations

import json
# comfyvn/server/core/logging_ex.py
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
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
        h = RotatingFileHandler(
            to_file,
            maxBytes=int(os.getenv("COMFYVN_LOG_MAXBYTES", "10485760")),
            backupCount=int(os.getenv("COMFYVN_LOG_BACKUPS", "5")),
        )
    else:
        h = logging.StreamHandler(sys.stdout)
    h.setLevel(level)
    h.setFormatter(fmt)
    return h


def _attach_special_logger(
    logger_name: str, file_path: Path, level: int, tag: str
) -> None:
    logger = logging.getLogger(logger_name)
    existing = [
        handler
        for handler in logger.handlers
        if getattr(handler, "_comfyvn_tag", None) == tag
    ]
    for handler in existing:
        logger.removeHandler(handler)
    handler = _mk_handler(str(file_path), level)
    setattr(handler, "_comfyvn_tag", tag)
    logger.addHandler(handler)
    if logger.level == logging.NOTSET or logger.level > level:
        logger.setLevel(level)
    logger.propagate = True


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

    # dedicated audio/advisory logs
    if to_file:
        log_dir = Path(to_file).resolve().parent
    else:
        log_dir = Path(os.getenv("COMFYVN_LOG_DIR", "logs")).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    audio_path = Path(os.getenv("COMFYVN_AUDIO_LOG_FILE", str(log_dir / "audio.log")))
    policy_path = Path(
        os.getenv("COMFYVN_POLICY_LOG_FILE", str(log_dir / "advisory.log"))
    )

    for name in (
        "comfyvn.audio",
        "comfyvn.audio.pipeline",
        "comfyvn.api.tts",
        "comfyvn.api.voice",
        "comfyvn.api.music",
    ):
        _attach_special_logger(name, audio_path, level, "audio")

    for name in (
        "comfyvn.advisory",
        "comfyvn.api.advisory",
        "comfyvn.api.policy",
    ):
        _attach_special_logger(name, policy_path, level, "policy")
