"""
Logging bootstrap for ComfyVN.

Creates a run-scoped directory in the user log folder and attaches rotating file + console handlers.
"""

from __future__ import annotations

import datetime
import logging
import pathlib
from logging.handlers import RotatingFileHandler
from typing import Tuple

from comfyvn.config.runtime_paths import logs_dir


def init_logging(run_tag: str = "session") -> Tuple[pathlib.Path, str]:
    logs_root = logs_dir()
    logs_root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_dir = logs_root / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        run_dir / "run.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    logging.getLogger(__name__).info("Logging initialized (run_id=%s, tag=%s)", run_id, run_tag)
    return run_dir, run_id
