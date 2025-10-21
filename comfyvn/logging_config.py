# [ComfyVN AutoPatch | Final Stage Sweep v0.4-pre | 2025-10-13]
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_FILE = "server.log"


def _coerce_level(level: str) -> int:
    try:
        return getattr(logging, level.upper())
    except AttributeError:
        return logging.INFO


def _resolve_base(path: Path) -> Path:
    if not path.is_absolute():
        return (REPO_ROOT / path).resolve()
    return path.resolve()


def default_log_dir() -> Path:
    override = os.getenv("COMFYVN_SERVER_LOG_DIR")
    if override:
        return _resolve_base(Path(override).expanduser())
    return _resolve_base(Path("logs"))


def init_logging(
    log_dir: str | os.PathLike[str] | None = None,
    *,
    level: str = "INFO",
    filename: str = DEFAULT_LOG_FILE,
) -> Path:
    """Initialise the root logger and write to repo-relative logs/server.log by default."""

    if log_dir:
        base = _resolve_base(Path(log_dir).expanduser())
    else:
        base = default_log_dir()
    base.mkdir(parents=True, exist_ok=True)
    log_path = base / filename

    root_logger = logging.getLogger()
    root_logger.setLevel(_coerce_level(level))

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    file_handler = RotatingFileHandler(
        str(log_path),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    os.environ.setdefault("COMFYVN_LOG_FILE", str(log_path))
    return log_path
