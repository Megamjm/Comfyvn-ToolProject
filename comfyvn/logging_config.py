# [ComfyVN AutoPatch | Final Stage Sweep v0.4-pre | 2025-10-13]
import os
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

from comfyvn.config.runtime_paths import logs_dir

def init_logging(log_dir: str | os.PathLike[str] | None = None, level: str = 'INFO', filename: str = 'system.log'):
    base = Path(log_dir) if log_dir else logs_dir()
    base.mkdir(parents=True, exist_ok=True)
    log_path = base / filename

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any existing handlers to avoid duplicate logs
    for h in list(logger.handlers):
        logger.removeHandler(h)

    handler = RotatingFileHandler(str(log_path), maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    # Do not add console handler so logs are batched to file only
    return log_path
