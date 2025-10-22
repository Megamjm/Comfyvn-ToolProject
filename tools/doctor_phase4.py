"""
Doctor Phase 4 — observability verification helper.

Usage:
    python tools/doctor_phase4.py [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfyvn.obs import capture_exception, get_logger


def _check_http(base_url: str) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/health"
    try:
        response = requests.get(url, timeout=3)
    except Exception as exc:  # pragma: no cover - network errors only
        return {"ok": False, "error": str(exc)}
    if response.status_code != 200:
        return {"ok": False, "status_code": response.status_code}
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return {"ok": True, "payload": payload}


def _simulate_crash() -> Dict[str, Any]:
    marker = time.time()
    exc = RuntimeError("doctor-phase4 simulated failure")
    report_path = capture_exception(
        exc,
        context={"doctor": "phase4", "marker": marker},
    )
    info = {"ok": False, "path": str(report_path)}
    try:
        payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
        info["payload"] = payload
        info["ok"] = payload.get("message") == str(exc)
    except Exception as exc_read:
        info["error"] = f"unreadable report: {exc_read}"
    return info


def _probe_structlog() -> Dict[str, Any]:
    logger = get_logger("doctor.phase4", component="doctor-phase4")
    try:
        logger.info("doctor-probe", extra={"probe": True})
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def run_doctor(base_url: str) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "http": _check_http(base_url),
        "crash_reporter": _simulate_crash(),
        "structlog": _probe_structlog(),
    }
    results["pass"] = all(
        check.get("ok") for check in results.values() if isinstance(check, dict)
    )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Doctor Phase 4 checks.")
    parser.add_argument(
        "--base",
        default="http://127.0.0.1:8000",
        help="Base URL for API probes (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    report = run_doctor(args.base)
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")

    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
