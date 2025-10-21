import logging
# [ComfyVN AutoPatch | Final Stage Sweep v0.4-pre | 2025-10-13]
import os
from logging.handlers import RotatingFileHandler

from PySide6.QtGui import QAction


def init_logging(
    log_dir: str = "logs", level: str = "INFO", filename: str = "system.log"
):
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, filename)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any existing handlers to avoid duplicate logs
    for h in list(logger.handlers):
        logger.removeHandler(h)

    handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    # Do not add console handler so logs are batched to file only
    return log_path
