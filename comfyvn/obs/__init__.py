"""
Observability utilities exposed for ComfyVN tooling.

This package currently provides:

* ``StructLogAdapter`` – light-weight structured logging helper that formats
  records as JSON payloads without depending on external logging frameworks.
* ``capture_exception`` – crash reporter helper that persists exception dumps
  to the user log directory.
* ``TelemetryStore`` – privacy-aware usage counters with anonymised payload
  helpers for modders and automation scripts.
* ``hash_identifier`` / ``anonymize_payload`` – utilities that produce
  consistent digests while scrubbing identifiers and long strings.
"""

from __future__ import annotations

from .anonymize import anonymize_payload, anonymous_installation_id, hash_identifier
from .crash_reporter import (
    capture_exception,
    install_sys_hook,
    last_report_path,
    report_path_for,
)
from .structlog_adapter import StructLogAdapter, get_logger
from .telemetry import TelemetrySettings, TelemetryStore, get_telemetry

__all__ = [
    "StructLogAdapter",
    "TelemetrySettings",
    "TelemetryStore",
    "anonymize_payload",
    "anonymous_installation_id",
    "capture_exception",
    "get_logger",
    "get_telemetry",
    "hash_identifier",
    "install_sys_hook",
    "last_report_path",
    "report_path_for",
]
