"""
Crash reporter helpers for ComfyVN.

Primary entrypoints:

* ``capture_exception`` – persist the supplied exception to a JSON file inside
  the user log directory (``logs/crash``).
* ``install_sys_hook`` – attach a defensive ``sys.excepthook`` that records
  uncaught exceptions using the same mechanism.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import traceback
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any, Mapping, MutableMapping, Optional, Sequence

from comfyvn.config.runtime_paths import logs_dir
from comfyvn.obs.structlog_adapter import get_logger, serialize_event

LOG = get_logger(__name__, component="crash-reporter")
_HOOK_INSTALLED = False
_LAST_REPORT: Path | None = None


def _crash_root() -> Path:
    root = logs_dir("crash")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _stamp() -> str:
    return _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _coerce_context(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    data = {}
    for key, value in payload.items():
        safe_key = str(key)
        try:
            repr(value)
        except Exception:
            value = "<unrepr-able>"
        data[safe_key] = value
    return data


def _format_traceback(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> str:
    return "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))


def report_path_for(event_id: Optional[str] = None) -> Path:
    slug = event_id or uuid.uuid4().hex[:8]
    name = f"crash-{_stamp()}-{slug}.json"
    return _crash_root() / name


def capture_exception(
    exc: BaseException,
    *,
    context: Mapping[str, Any] | None = None,
    event_id: Optional[str] = None,
    attach: Sequence[Path | str] | None = None,
) -> Path:
    """
    Persist a crash report JSON file for the supplied exception.

    Returns the file path written so callers can surface it to users.
    """

    exc_type = type(exc)
    report_path = report_path_for(event_id)

    frame = exc.__traceback__
    trace = _format_traceback(exc_type, exc, frame)

    attachments: list[str] = []
    for item in attach or ():
        try:
            path = Path(item)
            attachments.append(str(path.resolve()))
        except Exception:
            attachments.append(str(item))

    payload = {
        "event_id": event_id or report_path.stem.split("-")[-1],
        "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
        "exc_type": f"{exc_type.__module__}.{exc_type.__name__}",
        "message": str(exc),
        "traceback": trace,
        "cwd": str(Path.cwd()),
        "pid": os.getpid(),
        "context": _coerce_context(context),
        "attachments": attachments,
    }

    report_path.write_text(serialize_event(payload), encoding="utf-8")

    global _LAST_REPORT
    _LAST_REPORT = report_path

    try:
        from comfyvn.obs.telemetry import get_telemetry

        get_telemetry().register_crash_report(report_path)
    except Exception:
        LOG.debug("telemetry-crash-track-failed", extra={"report": str(report_path)})

    LOG.error(
        "crash",
        extra={
            "report": str(report_path),
            "exc_type": payload["exc_type"],
            "message": payload["message"],
        },
    )

    return report_path


def install_sys_hook(force: bool = False) -> None:
    """
    Install ``sys.excepthook`` to capture uncaught exceptions.

    The hook is idempotent unless ``force`` is passed.
    """

    global _HOOK_INSTALLED
    if _HOOK_INSTALLED and not force:
        return

    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_traceback):
        try:
            capture_exception(
                exc_value,
                context={"source": "sys.excepthook"},
                event_id=None,
            )
        except Exception:
            LOG.warning("crash-hook-failed", extra={"exc_type": str(exc_type)})
        finally:
            previous(exc_type, exc_value, exc_traceback)

    sys.excepthook = _hook
    _HOOK_INSTALLED = True


def last_report_path() -> Path | None:
    return _LAST_REPORT


def iter_reports(*, limit: int = 20) -> list[dict[str, Any]]:
    """
    Return crash report payloads newest-first up to ``limit`` entries.

    Only well-formed JSON payloads are included.
    """

    root = _crash_root()
    if not root.exists():
        return []

    files = sorted(root.glob("crash-*.json"), reverse=True)
    results: list[dict[str, Any]] = []
    for path in files:
        if len(results) >= max(limit, 1):
            break
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            data.setdefault("path", str(path))
            results.append(data)
    return results


__all__ = [
    "capture_exception",
    "install_sys_hook",
    "iter_reports",
    "last_report_path",
    "report_path_for",
]
