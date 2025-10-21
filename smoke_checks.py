from __future__ import annotations

import argparse
import sys
import time
from typing import Any, Mapping

import httpx

DEFAULT_BASE = "http://127.0.0.1:8001"


def _normalise_base(url: str) -> str:
    return url.rstrip("/")


def check_health(client: httpx.Client, base: str) -> float:
    start = time.perf_counter()
    response = client.get(f"{base}/health", timeout=2.0)
    elapsed = time.perf_counter() - start
    if response.status_code != 200:
        raise RuntimeError(f"/health returned HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise RuntimeError("/health did not return a JSON object")
    status = str(payload.get("status", "")).lower()
    ok = bool(payload.get("ok", status == "ok"))
    if not ok:
        raise RuntimeError(f"/health payload indicated failure: {payload}")
    return elapsed


def _require_numeric(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)):
        raise RuntimeError(f"/system/metrics missing numeric '{key}' (got {value!r})")
    return float(value)


def check_metrics(client: httpx.Client, base: str) -> Mapping[str, Any]:
    response = client.get(f"{base}/system/metrics", timeout=2.5)
    if response.status_code != 200:
        raise RuntimeError(f"/system/metrics returned HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise RuntimeError("/system/metrics did not return a JSON object")
    if not bool(payload.get("ok", True)):
        raise RuntimeError(f"/system/metrics payload indicated failure: {payload}")

    cpu = _require_numeric(payload, "cpu")
    mem = _require_numeric(payload, "mem")
    disk = _require_numeric(payload, "disk")

    if not (0 <= cpu <= 100):
        raise RuntimeError(f"CPU percent out of range: {cpu}")
    if not (0 <= mem <= 100):
        raise RuntimeError(f"Memory percent out of range: {mem}")
    if not (0 <= disk <= 100):
        raise RuntimeError(f"Disk percent out of range: {disk}")

    gpus = payload.get("gpus")
    if gpus is not None and not isinstance(gpus, list):
        raise RuntimeError("Expected 'gpus' to be a list")

    if gpus:
        first_gpu = payload.get("first_gpu") or gpus[0]
        if not isinstance(first_gpu, Mapping):
            raise RuntimeError("Expected 'first_gpu' to be an object")

    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ComfyVN smoke checks for core health and metrics."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE,
        help=f"Base URL for the ComfyVN server (default: {DEFAULT_BASE})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base = _normalise_base(args.base_url)

    print(f"[smoke] Target base URL: {base}")
    try:
        with httpx.Client() as client:
            elapsed = check_health(client, base)
            print(f"[smoke] /health OK in {elapsed * 1000:.1f} ms")
            metrics = check_metrics(client, base)
            print(
                "[smoke] /system/metrics OK — "
                f"CPU {metrics.get('cpu')}% | MEM {metrics.get('mem')}% | DISK {metrics.get('disk')}%"
            )
            gpus = metrics.get("gpus") or []
            if gpus:
                first = metrics.get("first_gpu") or gpus[0]
                name = first.get("name", "GPU")
                util = first.get("util", first.get("utilization"))
                print(f"[smoke] First GPU: {name} @ {util}% util")
            else:
                print("[smoke] No GPU metrics reported (CPU-only host)")
    except Exception as exc:
        print(f"[smoke] FAILED: {exc}", file=sys.stderr)
        return 1

    print("[smoke] All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
