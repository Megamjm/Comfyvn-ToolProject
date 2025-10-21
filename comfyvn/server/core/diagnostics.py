import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/server/core/diagnostics.py
# 🧠 Diagnostics — collects startup info, errors, and saves reports

import datetime
import json
import os

from comfyvn.config.runtime_paths import diagnostics_dir

LOG_PATH = diagnostics_dir()
LOG_PATH.mkdir(parents=True, exist_ok=True)
REPORT_FILE = diagnostics_dir("startup_report.json")

_startup_log = {
    "timestamp": datetime.datetime.now().isoformat(),
    "events": [],
}


def log_diagnostic(section: str, data):
    """Append diagnostic data under a labeled section."""
    _startup_log["events"].append({"section": section, "data": data})
    print(f"[Diagnostics] {section}: {data}")


def dump_startup_report():
    """Write startup diagnostics to JSON report."""
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(_startup_log, f, indent=2)
    print(f"[Diagnostics] 🧾 Startup report written to {REPORT_FILE}")
