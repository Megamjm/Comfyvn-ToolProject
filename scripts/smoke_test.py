#!/usr/bin/env python3
"""Lightweight smoke test against a running ComfyVN instance.

The script hits the canonical readiness endpoints and optionally uploads a
roleplay text file so PR authors can validate core integrations quickly.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

import httpx


DEFAULT_ENDPOINTS: tuple[str, ...] = ("/health", "/system/metrics")
DEFAULT_UPLOAD_ENDPOINT = "/system/roleplay"
DEFAULT_BASE_URL = "http://localhost:8001"


def _format_endpoint_results(results: Iterable[tuple[str, int | None, str]]) -> str:
    """Return a compact status summary for stdout."""
    lines = []
    for endpoint, status_code, payload_hint in results:
        status_display = status_code if status_code is not None else "ERROR"
        lines.append(f"{endpoint:20} -> {status_display} {payload_hint}")
    return "\n".join(lines)


def run_http_checks(base_url: str, endpoints: Iterable[str], timeout: float) -> bool:
    """Hit the provided list of endpoints and log their status codes."""
    client = httpx.Client(base_url=base_url, timeout=timeout, follow_redirects=True)
    results = []
    ok = True
    for endpoint in endpoints:
        try:
            resp = client.get(endpoint)
            resp.raise_for_status()
            payload_hint = resp.headers.get("content-type", "")[:32]
            results.append((endpoint, resp.status_code, payload_hint))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            ok = False
            results.append((endpoint, None, f"{exc}"))
    print("== HTTP smoke checks ==")
    print(_format_endpoint_results(results))
    return ok


def maybe_upload_roleplay(
    base_url: str, timeout: float, upload_path: Path | None, upload_endpoint: str
) -> bool:
    """Upload a roleplay text file, if provided."""
    if upload_path is None:
        return True
    if not upload_path.exists():
        print(f"[warn] roleplay file not found: {upload_path}")
        return False
    with httpx.Client(base_url=base_url, timeout=timeout, follow_redirects=True) as client:
        try:
            payload = upload_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            payload = upload_path.read_text(encoding="latin-1")
        try:
            resp = client.post(
                upload_endpoint,
                files={"file": (upload_path.name, payload.encode("utf-8"), "text/plain")},
            )
            resp.raise_for_status()
            print(f"Uploaded roleplay sample to {upload_endpoint}: {resp.status_code}")
            return True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[warn] roleplay upload failed: {exc}")
            return False


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run HTTP smoke tests against a ComfyVN deployment."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("COMFYVN_BASE_URL", DEFAULT_BASE_URL),
        help=f"Root URL for the service (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--endpoints",
        nargs="+",
        default=list(DEFAULT_ENDPOINTS),
        help="List of endpoints to check (default: %(default)s)",
    )
    parser.add_argument(
        "--roleplay-file",
        type=Path,
        help="Optional text file to upload as part of the smoke test.",
    )
    parser.add_argument(
        "--upload-endpoint",
        default=DEFAULT_UPLOAD_ENDPOINT,
        help=f"Endpoint used when uploading roleplay text (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    print(f"Running smoke test against {args.base_url}")
    http_ok = run_http_checks(args.base_url, args.endpoints, args.timeout)
    upload_ok = maybe_upload_roleplay(
        args.base_url, args.timeout, args.roleplay_file, args.upload_endpoint
    )
    return 0 if (http_ok and upload_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
