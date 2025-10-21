from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Coroutine, Dict, Optional

from comfyvn.bridge.comfy import ComfyBridgeError, ComfyUIBridge, RenderContext

LOGGER = logging.getLogger(__name__)


class ComfyBridge:
    """Thread-safe convenience wrapper around :class:`ComfyUIBridge`."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188") -> None:
        self._bridge = ComfyUIBridge(base_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_base(self, base: str) -> None:
        self._bridge.set_base_url(base)

    def ping(self) -> Dict[str, Any]:
        return self._run_sync(self.ping_async())

    async def ping_async(self) -> Dict[str, Any]:
        try:
            stats = await self._bridge.ping()
            return {"ok": True, "base": self.base_url, "stats": stats}
        except (
            Exception
        ) as exc:  # pragma: no cover - network failures depend on environment
            LOGGER.warning("Comfy bridge ping failed: %s", exc)
            return {"ok": False, "base": self.base_url, "error": str(exc)}

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._run_sync(self.submit_async(payload))

    async def submit_async(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        workflow = self._resolve_workflow(payload)
        context = self._build_context(payload)
        poll_interval = float(payload.get("poll_interval", 1.5))
        timeout = float(payload.get("timeout", 300.0))

        download_dir: Optional[Path] = None
        if payload.get("download_dir"):
            download_dir = Path(payload["download_dir"]).expanduser()
            download_dir.mkdir(parents=True, exist_ok=True)

        downloaded: Optional[list[str]] = None
        try:
            result = await self._bridge.run_workflow(
                workflow,
                context=context,
                poll_interval=poll_interval,
                timeout=timeout,
                download_dir=None,
            )
            if download_dir:
                paths = await self._bridge.download_artifacts(result, download_dir)
                downloaded = [str(path) for path in paths]
        except ComfyBridgeError as exc:
            LOGGER.error("Comfy workflow failed: %s", exc)
            return {
                "ok": False,
                "error": str(exc),
                "workflow_id": context.workflow_id,
            }

        payload = result.to_dict()
        payload["ok"] = True
        payload["base"] = self.base_url
        if download_dir:
            payload["downloaded"] = downloaded or []
        return payload

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return self._bridge.base_url

    def _run_sync(self, coro: Coroutine[Any, Any, Any]) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError(
            "ComfyBridge synchronous methods cannot be invoked inside an active event loop; "
            "use the async variants instead."
        )

    def _resolve_workflow(self, payload: Dict[str, Any]) -> Any:
        if "workflow" in payload:
            return payload["workflow"]
        if "graph" in payload:
            return payload["graph"]
        if "prompt" in payload:
            return payload["prompt"]
        if payload.get("workflow_path"):
            return Path(payload["workflow_path"]).expanduser()
        raise ValueError(
            "payload must include 'workflow', 'graph', 'prompt', or 'workflow_path'"
        )

    def _build_context(self, payload: Dict[str, Any]) -> RenderContext:
        workflow_id = str(
            payload.get("workflow_id") or payload.get("id") or "comfyvn.workflow"
        )
        return RenderContext(
            workflow_id=workflow_id,
            inputs=dict(payload.get("inputs") or {}),
            packs=dict(payload.get("packs") or {}),
            pins=dict(payload.get("pins") or {}),
            metadata=dict(payload.get("metadata") or {}),
            seeds=dict(payload.get("seeds") or {}),
            tags=dict(payload.get("tags") or {}),
        )


__all__ = ["ComfyBridge"]
