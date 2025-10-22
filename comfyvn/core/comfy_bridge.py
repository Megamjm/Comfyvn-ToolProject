from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Coroutine, Dict, List, Optional

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

        enable_preview = bool(payload.get("preview_stream", False))
        preview_root = payload.get("preview_dir") or "data/cache/comfy_previews"
        base_preview_dir: Optional[Path] = None
        if enable_preview:
            try:
                base_preview_dir = Path(preview_root).expanduser() / context.workflow_id
            except Exception:  # pragma: no cover - defensive
                base_preview_dir = Path(preview_root) / context.workflow_id

        enable_resume = bool(payload.get("resume_on_error", enable_preview))
        max_attempts = int(payload.get("resume_attempts", 2 if enable_resume else 1))
        if max_attempts < 1:
            max_attempts = 1

        downloaded: Optional[list[str]] = None
        resume_attempts: List[Dict[str, Any]] = []
        result = None
        attempt_index = 0
        last_error: Optional[ComfyBridgeError] = None

        while attempt_index < max_attempts:
            attempt_index += 1
            attempt_preview_dir: Optional[Path] = None
            if base_preview_dir is not None:
                attempt_preview_dir = base_preview_dir / f"attempt_{attempt_index}"
            try:
                result = await self._bridge.run_workflow(
                    workflow,
                    context=context,
                    poll_interval=poll_interval,
                    timeout=timeout,
                    download_dir=None,
                    preview_dir=attempt_preview_dir,
                )
                break
            except ComfyBridgeError as exc:
                last_error = exc
                resume_attempts.append(
                    {
                        "attempt": attempt_index,
                        "error": str(exc),
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                )
                if not enable_resume or attempt_index >= max_attempts:
                    LOGGER.error("Comfy workflow failed: %s", exc)
                    return {
                        "ok": False,
                        "error": str(exc),
                        "workflow_id": context.workflow_id,
                        "resume": {
                            "attempts": resume_attempts,
                            "recovered": False,
                        },
                    }
                LOGGER.warning(
                    "Comfy workflow failed (%s); retrying (%d/%d)",
                    exc,
                    attempt_index + 1,
                    max_attempts,
                )
                await asyncio.sleep(min(5.0, poll_interval * 2))

        if result is None:
            if last_error is not None:
                raise last_error
            raise ComfyBridgeError("Comfy workflow did not produce a result")

        if download_dir:
            paths = await self._bridge.download_artifacts(result, download_dir)
            downloaded = [str(path) for path in paths]

        payload = result.to_dict()
        payload["ok"] = True
        payload["base"] = self.base_url
        if download_dir:
            payload["downloaded"] = downloaded or []
        if resume_attempts:
            payload["resume"] = {
                "attempts": resume_attempts,
                "recovered": True,
                "total_attempts": attempt_index,
            }
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
