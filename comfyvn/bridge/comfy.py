from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
)

import httpx

if TYPE_CHECKING:
    from comfyvn.bridge.comfy_stream import PreviewCollector

LOGGER = logging.getLogger(__name__)


class ComfyBridgeError(RuntimeError):
    """Raised when communication with ComfyUI fails or returns an invalid payload."""


@dataclass(slots=True)
class RenderContext:
    """Metadata bundled with every ComfyUI job submission."""

    workflow_id: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    packs: Dict[str, Any] = field(default_factory=dict)
    pins: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    seeds: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "inputs": self.inputs,
            "packs": self.packs,
            "pins": self.pins,
            "metadata": self.metadata,
            "seeds": self.seeds,
            "tags": self.tags,
        }


@dataclass(slots=True)
class ArtifactDescriptor:
    """Describes an image/video/audio artifact produced by a workflow."""

    prompt_id: str
    node_id: str
    kind: str
    filename: str
    subfolder: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_params(self) -> Dict[str, str]:
        return {
            "filename": self.filename,
            "subfolder": self.subfolder or "",
            "type": self.kind or "output",
        }


@dataclass(slots=True)
class RenderJob:
    """Represents a queued workflow inside ComfyUI."""

    prompt_id: str
    queued_at: float
    context: RenderContext
    workflow: Dict[str, Any]
    envelope: Dict[str, Any]


@dataclass(slots=True)
class RenderResult:
    """Holds the final history payload and resolved artifacts."""

    job: RenderJob
    record: Dict[str, Any]
    artifacts: List[ArtifactDescriptor]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_id": self.job.prompt_id,
            "workflow_id": self.job.context.workflow_id,
            "history": self.record,
            "artifacts": [
                {
                    "filename": art.filename,
                    "subfolder": art.subfolder,
                    "type": art.kind,
                    "node_id": art.node_id,
                    "metadata": art.metadata,
                }
                for art in self.artifacts
            ],
            "context": self.job.context.to_payload(),
        }


class ComfyUIBridge:
    """Async helper that wraps ComfyUI's REST interface with retries and metadata logging."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        *,
        request_timeout: float = 10.0,
        read_timeout: float = 90.0,
        max_retries: int = 3,
        retry_backoff: float = 1.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self.read_timeout = read_timeout
        self.max_retries = max(1, max_retries)
        self.retry_backoff = max(0.2, retry_backoff)
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ Lifecycle ------------------------------------------------------------------
    async def __aenter__(self) -> "ComfyUIBridge":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        async with self._lock:
            if self._client:
                await self._client.aclose()
                self._client = None

    def set_base_url(self, base_url: str) -> None:
        self.base_url = (base_url or "http://127.0.0.1:8188").rstrip("/")

    async def _ensure_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None:
                timeout = httpx.Timeout(
                    self.request_timeout,
                    connect=self.request_timeout,
                    read=self.read_timeout,
                    write=self.request_timeout,
                )
                self._client = httpx.AsyncClient(timeout=timeout)
        return self._client  # type: ignore[return-value]

    # ------------------------------------------------------------------ Public API ------------------------------------------------------------------
    async def ping(self) -> Dict[str, Any]:
        """Return ComfyUI system stats, raising if the instance is unreachable."""
        client = await self._ensure_client()
        response = await client.get(f"{self.base_url}/system_stats")
        response.raise_for_status()
        return response.json()

    async def queue_prompt(
        self,
        workflow: Dict[str, Any] | Path | str,
        *,
        context: RenderContext,
    ) -> RenderJob:
        """Submit a workflow and return the queued job."""
        graph, envelope = self._normalise_workflow(workflow)
        payload = self._build_prompt_payload(graph, context, envelope=envelope)

        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt < self.max_retries:
            try:
                client = await self._ensure_client()
                response = await client.post(f"{self.base_url}/prompt", json=payload)
                response.raise_for_status()
                data = response.json()
                prompt_id = str(
                    data.get("prompt_id") or data.get("promptID") or ""
                ).strip()
                if not prompt_id:
                    raise ComfyBridgeError("ComfyUI did not return a prompt_id")
                LOGGER.debug(
                    "Queued ComfyUI job %s (%s) packs=%s pins=%s seeds=%s",
                    prompt_id,
                    context.workflow_id,
                    list(context.packs.keys()),
                    list(context.pins.keys()),
                    {k: v for k, v in context.seeds.items()},
                )
                return RenderJob(
                    prompt_id=prompt_id,
                    queued_at=time.time(),
                    context=context,
                    workflow=graph,
                    envelope=envelope,
                )
            except (
                httpx.HTTPStatusError
            ) as exc:  # pragma: no cover - network errors hard to reproduce
                last_exc = exc
                LOGGER.warning(
                    "ComfyUI prompt submission failed (%s): %s",
                    exc.response.status_code,
                    exc,
                )
            except Exception as exc:  # pragma: no cover - defensive
                last_exc = exc
                LOGGER.warning("ComfyUI prompt submission error: %s", exc)

            attempt += 1
            await asyncio.sleep(self.retry_backoff * attempt)

        raise ComfyBridgeError(
            f"Failed to submit workflow after {self.max_retries} attempts"
        ) from last_exc

    async def fetch_history(self, prompt_id: str) -> Dict[str, Any]:
        """Fetch the raw history payload for a prompt."""
        if not prompt_id:
            raise ValueError("prompt_id is required")
        client = await self._ensure_client()
        response = await client.get(f"{self.base_url}/history/{prompt_id}")
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        try:
            return response.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ComfyBridgeError("ComfyUI returned invalid JSON for history") from exc

    async def wait_for_result(
        self,
        job: RenderJob,
        *,
        poll_interval: float = 1.5,
        timeout: float = 300.0,
        terminal_statuses: Optional[Sequence[str]] = None,
        preview_collector: Optional["PreviewCollector"] = None,
    ) -> RenderResult:
        """Poll history until the prompt completes or fails."""
        deadline = time.monotonic() + timeout
        last_status: Optional[str] = None
        desired = {
            status.lower()
            for status in (terminal_statuses or ("completed", "success", "finished"))
        }
        failure_states = {"failed", "error", "cancelled", "canceled"}
        client = await self._ensure_client()

        while time.monotonic() < deadline:
            payload = await self.fetch_history(job.prompt_id)
            record = self._extract_history_record(payload, job.prompt_id)
            if record:
                if preview_collector:
                    try:
                        await preview_collector.collect(
                            client,
                            record,
                            prompt_id=job.prompt_id,
                            base_url=self.base_url,
                        )
                    except Exception:  # pragma: no cover - defensive
                        LOGGER.debug("Preview collection failed", exc_info=True)
                status = str(record.get("status") or "").lower()
                if status in desired:
                    artifacts = self._collect_artifacts(job.prompt_id, record)
                    return RenderResult(job=job, record=record, artifacts=artifacts)
                if status in failure_states:
                    raise ComfyBridgeError(f"ComfyUI workflow failed ({status})")
                last_status = status or last_status
            await asyncio.sleep(poll_interval)

        raise ComfyBridgeError(
            f"Timed out waiting for ComfyUI prompt {job.prompt_id} "
            f"(workflow={job.context.workflow_id}, last_status={last_status})"
        )

    async def run_workflow(
        self,
        workflow: Dict[str, Any] | Path | str,
        *,
        context: RenderContext,
        poll_interval: float = 1.5,
        timeout: float = 300.0,
        download_dir: Optional[Path] = None,
        preview_dir: Optional[Path] = None,
        preview_callback: Optional[
            Callable[[Dict[str, Any]], Optional[Awaitable[None]]]
        ] = None,
    ) -> RenderResult:
        """Submit, wait, and optionally download artifacts for a workflow."""
        job = await self.queue_prompt(workflow, context=context)
        preview_collector: Optional["PreviewCollector"] = None
        if preview_dir is not None:
            try:
                from comfyvn.bridge.comfy_stream import PreviewCollector
            except Exception:  # pragma: no cover - optional path
                PreviewCollector = None  # type: ignore
            if PreviewCollector is not None:
                try:
                    base = preview_dir.expanduser().resolve()
                except Exception:
                    base = preview_dir
                preview_collector = PreviewCollector(
                    base / job.prompt_id, notifier=preview_callback
                )
        result = await self.wait_for_result(
            job,
            poll_interval=poll_interval,
            timeout=timeout,
            preview_collector=preview_collector,
        )
        if download_dir:
            await self.download_artifacts(result, download_dir)
        if preview_collector:
            try:
                preview_collector.finalize(result)
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("Preview collector finalize failed", exc_info=True)
        return result

    async def download_artifacts(
        self, result: RenderResult, target_dir: Path
    ) -> List[Path]:
        """Download all artifacts from a completed job into the provided directory."""
        target_dir.mkdir(parents=True, exist_ok=True)
        client = await self._ensure_client()
        saved_paths: List[Path] = []
        for artifact in result.artifacts:
            params = artifact.to_params()
            response = await client.get(f"{self.base_url}/view", params=params)
            if response.status_code == 404:
                LOGGER.warning("Artifact missing on ComfyUI disk: %s", params)
                continue
            response.raise_for_status()
            dest = target_dir / artifact.filename
            dest.write_bytes(response.content)
            saved_paths.append(dest)
            LOGGER.debug("Downloaded artifact %s to %s", artifact.filename, dest)
        return saved_paths

    # ------------------------------------------------------------------ Internal helpers ------------------------------------------------------------------
    def _normalise_workflow(
        self,
        workflow: Dict[str, Any] | Path | str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        if isinstance(workflow, (str, Path)):
            path = Path(workflow)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - defensive
                raise ComfyBridgeError(f"Failed to load workflow JSON: {path}") from exc
        else:
            data = workflow

        if not isinstance(data, dict):
            raise ComfyBridgeError("Workflow payload must be a JSON object")

        envelope = dict(data)
        for key in ("workflow", "graph"):
            if key in data and isinstance(data[key], dict):
                return data[key], envelope

        if "nodes" in data and "links" in data:
            return data, envelope

        raise ComfyBridgeError(
            "Workflow JSON missing graph definition ('workflow'/'graph'/'nodes')"
        )

    def _build_prompt_payload(
        self,
        graph: Dict[str, Any],
        context: RenderContext,
        *,
        envelope: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {"prompt": graph}
        meta = context.to_payload()
        if envelope:
            # Shallow copy to avoid mutating original
            meta["workflow_version"] = envelope.get("version")
            meta["family"] = envelope.get("family")
            if envelope.get("metadata"):
                meta["workflow_meta"] = envelope.get("metadata")
        payload["extra_data"] = {"comfyvn": meta}
        return payload

    def _extract_history_record(
        self, payload: Dict[str, Any], prompt_id: str
    ) -> Dict[str, Any]:
        if not payload:
            return {}
        history = payload.get("history")
        if isinstance(history, dict):
            record = history.get(prompt_id)
            if isinstance(record, dict):
                return record
        record = payload.get(prompt_id)
        if isinstance(record, dict):
            return record
        return {}

    def _collect_artifacts(
        self, prompt_id: str, record: Dict[str, Any]
    ) -> List[ArtifactDescriptor]:
        outputs = record.get("outputs") or {}
        descriptors: List[ArtifactDescriptor] = []
        for node_id, node_outputs in outputs.items():
            if not isinstance(node_outputs, list):
                continue
            for entry in node_outputs:
                filename = entry.get("filename")
                if not filename:
                    continue
                descriptor = ArtifactDescriptor(
                    prompt_id=prompt_id,
                    node_id=str(node_id),
                    kind=str(entry.get("type") or "output"),
                    filename=str(filename),
                    subfolder=str(entry.get("subfolder") or ""),
                    metadata={
                        "seed": entry.get("seed"),
                        "workflow": entry.get("workflow"),
                        "width": entry.get("width"),
                        "height": entry.get("height"),
                        "extra": entry.get("metadata") or {},
                    },
                )
                descriptors.append(descriptor)
        return descriptors


__all__ = [
    "ArtifactDescriptor",
    "ComfyBridgeError",
    "ComfyUIBridge",
    "RenderContext",
    "RenderJob",
    "RenderResult",
]
