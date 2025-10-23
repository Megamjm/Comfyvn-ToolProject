from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

LOGGER = logging.getLogger(__name__)


def _coerce_base(provider: Dict[str, Any]) -> str:
    value = (
        provider.get("base_url")
        or provider.get("base")
        or provider.get("endpoint")
        or ""
    )
    return str(value).strip()


@dataclass(slots=True)
class EchoAdapter:
    """Minimal remote adapter that probes a configurable echo endpoint."""

    base_url: str
    timeout: float = 5.0

    @classmethod
    def from_provider(
        cls, provider: Dict[str, Any], *, timeout: float = 5.0
    ) -> "EchoAdapter":
        return cls(base_url=_coerce_base(provider), timeout=timeout)

    async def health(self) -> Dict[str, Any]:
        """Perform a lightweight GET against the echo service."""

        start = time.perf_counter()
        base = self.base_url
        if not base or base.startswith(("stub://", "memory://")):
            elapsed = int((time.perf_counter() - start) * 1000)
            return {"ok": True, "latency_ms": elapsed, "echo": True}

        url = base.rstrip("/")
        if not url.endswith("/health"):
            url = f"{url}/health"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
            elapsed = int((time.perf_counter() - start) * 1000)
            payload: Dict[str, Any]
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type.lower():
                try:
                    payload = response.json()
                except Exception:
                    payload = {"body": response.text}
            else:
                payload = {"body": response.text}
            return {
                "ok": response.status_code < 500,
                "latency_ms": elapsed,
                "status_code": response.status_code,
                "payload": payload,
            }
        except Exception as exc:  # pragma: no cover - network failures
            elapsed = int((time.perf_counter() - start) * 1000)
            LOGGER.debug("EchoAdapter health failed for %s: %s", self.base_url, exc)
            return {"ok": False, "error": str(exc), "latency_ms": elapsed}

    async def fetch_quota(self) -> Dict[str, Any]:
        return {"ok": False, "error": "quota unsupported for echo adapter"}

    async def fetch_templates(self) -> Dict[str, Any]:
        return {"ok": False, "error": "templates unsupported for echo adapter"}

    async def bootstrap(
        self,
        *,
        output_dir,
        workspace=None,
        log_hook: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if log_hook:
            log_hook("Echo adapter bootstrap invoked (noop).")
        return {"ok": True, "artifacts": []}
