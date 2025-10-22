from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from comfyvn.core import compute_providers as generic_providers

LOGGER = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_templates(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        candidates = (
            payload.get("data")
            or payload.get("items")
            or payload.get("podTemplates")
            or payload.get("templates")
            or payload.get("results")
            or []
        )
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []

    templates: List[Dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        template_id = str(
            item.get("id")
            or item.get("templateId")
            or item.get("podTemplateId")
            or item.get("name")
            or ""
        ).strip()
        if not template_id:
            continue
        hourly = (
            item.get("hourlyPrice")
            or item.get("price")
            or item.get("costPerHour")
            or item.get("hourlyUsd")
        )
        templates.append(
            {
                "id": template_id,
                "name": item.get("name") or item.get("label") or template_id,
                "gpu": item.get("gpu") or item.get("gpuName") or item.get("gpuType"),
                "gpu_count": item.get("gpuCount") or item.get("numGPUs"),
                "memory_gb": item.get("memoryInGb")
                or item.get("memory")
                or item.get("systemMemory"),
                "storage_gb": item.get("storageInGb")
                or item.get("disk")
                or item.get("storage"),
                "region": item.get("region")
                or item.get("gpuLocation")
                or item.get("availabilityZone"),
                "image": item.get("imageName")
                or item.get("dockerImage")
                or item.get("image")
                or item.get("containerImage"),
                "hourly_usd": _safe_float(hourly),
                "raw": item,
            }
        )
    return templates


def _coerce_quota(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"raw": payload}

    credits_remaining = (
        payload.get("creditsRemaining")
        or payload.get("creditBalance")
        or payload.get("credits")
        or payload.get("balance")
    )
    credits_total = (
        payload.get("creditsTotal")
        or payload.get("creditLimit")
        or payload.get("quota")
        or payload.get("limit")
    )
    credits_used = (
        payload.get("creditsUsed")
        or payload.get("usage")
        or payload.get("consumed")
        or payload.get("spent")
    )
    plan = payload.get("plan") or payload.get("subscription") or {}

    return {
        "credits_remaining": _safe_float(credits_remaining),
        "credits_total": _safe_float(credits_total),
        "credits_used": _safe_float(credits_used),
        "currency": payload.get("currency") or "USD",
        "plan": plan if isinstance(plan, dict) else {"name": plan},
        "raw": payload,
    }


def _artifact_summary(paths: List[Path]) -> List[str]:
    return [str(path) for path in paths]


@dataclass(slots=True)
class RunPodAdapter:
    base_url: str
    api_key: Optional[str] = None
    project_id: Optional[str] = None
    timeout: float = 15.0
    client: Optional[httpx.AsyncClient] = field(default=None, repr=False)

    @classmethod
    def from_provider(
        cls, provider: Dict[str, Any], *, timeout: float = 15.0
    ) -> "RunPodAdapter":
        base = str(
            provider.get("base_url")
            or provider.get("base")
            or provider.get("endpoint")
            or ""
        ).strip()
        config = provider.get("config") or {}
        meta = provider.get("meta") or {}
        api_key = (
            config.get("api_key")
            or meta.get("api_key")
            or provider.get("auth")
            or provider.get("token")
        )
        project = config.get("project_id") or meta.get("project_id")
        return cls(base_url=base, api_key=api_key, project_id=project, timeout=timeout)

    # ------------------------------------------------------------------ internal helpers
    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url.rstrip("/") + path

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update(extra)
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        url = self._url(path)
        request_headers = self._headers(headers)
        client = self.client
        if client is not None:
            response = await client.request(
                method, url, headers=request_headers, timeout=self.timeout, **kwargs
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as session:
                response = await session.request(
                    method, url, headers=request_headers, **kwargs
                )
        response.raise_for_status()
        return response

    def _elapsed_ms(self, response: httpx.Response) -> Optional[int]:
        try:
            elapsed = getattr(response, "elapsed", None)
        except RuntimeError:
            return None
        if elapsed is None:
            return None
        try:
            return int(elapsed.total_seconds() * 1000)
        except Exception:
            return None

    # ------------------------------------------------------------------ public helpers
    async def health(self) -> Dict[str, Any]:
        """Lightweight health probe using the pod template listing."""
        if not self.base_url:
            return {"ok": False, "error": "base_url missing"}

        try:
            response = await self._request("GET", "/pod-templates")
        except httpx.HTTPStatusError as exc:
            LOGGER.warning("RunPod health failed (%s)", exc)
            return {
                "ok": False,
                "status_code": exc.response.status_code,
                "error": str(exc),
            }
        except Exception as exc:  # pragma: no cover - network dependent
            LOGGER.warning("RunPod health error: %s", exc)
            return {"ok": False, "error": str(exc)}

        templates = _coerce_templates(response.json())
        return {
            "ok": True,
            "templates": len(templates),
            "latency_ms": self._elapsed_ms(response),
        }

    async def fetch_templates(self) -> Dict[str, Any]:
        """Return available pod templates with normalized metadata."""
        if not self.base_url:
            return {"ok": False, "error": "base_url missing"}
        try:
            response = await self._request("GET", "/pod-templates")
        except httpx.HTTPStatusError as exc:
            return {
                "ok": False,
                "status_code": exc.response.status_code,
                "error": str(exc),
            }
        except Exception as exc:  # pragma: no cover - network dependent
            return {"ok": False, "error": str(exc)}
        templates = _coerce_templates(response.json())
        return {
            "ok": True,
            "templates": templates,
            "latency_ms": self._elapsed_ms(response),
        }

    async def fetch_quota(self) -> Dict[str, Any]:
        """Return account quota/credit details (best-effort)."""
        if not self.base_url:
            return {"ok": False, "error": "base_url missing"}

        candidate_paths: Tuple[str, ...] = (
            "/account",
            "/user/account",
            "/profile",
            "/account/credits",
        )
        last_error: Optional[Dict[str, Any]] = None
        for path in candidate_paths:
            try:
                response = await self._request("GET", path)
                quota = _coerce_quota(response.json())
                return {
                    "ok": True,
                    "quota": quota,
                    "latency_ms": self._elapsed_ms(response),
                    "endpoint": self._url(path),
                }
            except httpx.HTTPStatusError as exc:
                last_error = {
                    "ok": False,
                    "status_code": exc.response.status_code,
                    "error": str(exc),
                    "endpoint": self._url(path),
                }
            except Exception as exc:  # pragma: no cover - network dependent
                last_error = {
                    "ok": False,
                    "error": str(exc),
                    "endpoint": self._url(path),
                }
        return last_error or {"ok": False, "error": "quota endpoint not reachable"}

    async def comfyui_health(self, base_url: Optional[str] = None) -> Dict[str, Any]:
        """Delegate to the shared ComfyUI health probe in a worker thread."""
        target = (base_url or self.base_url or "").strip()
        if not target:
            return {"ok": False, "error": "base_url missing"}

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: generic_providers.comfyui_health(target)
        )

    async def bootstrap(
        self,
        *,
        output_dir: Path,
        workspace: Optional[Path] = None,
        log_hook: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Collect templates/quota data and snapshot workspace metadata."""
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        logs: List[str] = []
        artifacts: List[Path] = []

        def _emit(message: str) -> None:
            logs.append(message)
            LOGGER.info("[RunPod bootstrap] %s", message)
            if log_hook:
                try:
                    log_hook(message)
                except Exception:  # pragma: no cover - defensive
                    LOGGER.debug("RunPod bootstrap log hook failed", exc_info=True)

        _emit("Starting RunPod bootstrap workflow")
        if not self.api_key:
            _emit("No API key provided; continuing with unauthenticated requests")

        # Fetch pod templates
        templates_result = await self.fetch_templates()
        if templates_result.get("ok"):
            templates_path = output_dir / "runpod_templates.json"
            templates_path.write_text(
                json.dumps(templates_result["templates"], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            artifacts.append(templates_path)
            _emit(
                f"Captured {len(templates_result['templates'])} pod template(s) -> {templates_path}"
            )
        else:
            _emit(
                f"Template discovery failed: {templates_result.get('error') or templates_result.get('status_code')}"
            )

        # Fetch quota information
        quota_result = await self.fetch_quota()
        if quota_result.get("ok"):
            quota_path = output_dir / "runpod_quota.json"
            quota_path.write_text(
                json.dumps(quota_result["quota"], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            artifacts.append(quota_path)
            _emit(f"Recorded quota details -> {quota_path}")
        elif quota_result:
            _emit(
                f"Quota probe failed via {quota_result.get('endpoint')}: {quota_result.get('error') or quota_result.get('status_code')}"
            )

        # Optionally index the workspace for later rsync operations
        workspace_manifest: Optional[Path] = None
        if workspace and workspace.exists():
            files: List[str] = []
            for path in workspace.rglob("*"):
                if path.is_file():
                    try:
                        rel = path.relative_to(workspace)
                    except ValueError:
                        rel = path.name
                    files.append(str(rel))
            manifest = {
                "root": str(workspace),
                "files": files,
                "total_files": len(files),
            }
            workspace_manifest = output_dir / "workspace_manifest.json"
            workspace_manifest.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            artifacts.append(workspace_manifest)
            _emit(
                f"Indexed local workspace ({manifest['total_files']} file(s)) -> {workspace_manifest}"
            )
        else:
            _emit("Workspace directory not provided or missing; skipping rsync index")

        # Probe downstream ComfyUI endpoint if configured.
        comfy_base = None
        provider_url_hint = self.base_url.rstrip("/")
        if provider_url_hint.endswith("/v2"):
            # Many RunPod deployments expose ComfyUI on a separate endpoint.
            comfy_base = provider_url_hint[:-3]
        comfy_probe = await self.comfyui_health(comfy_base)
        comfy_status_path = output_dir / "comfyui_health.json"
        comfy_status_path.write_text(
            json.dumps(comfy_probe, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        artifacts.append(comfy_status_path)
        if comfy_probe.get("ok"):
            _emit(f"Verified ComfyUI backend -> {comfy_probe}")
        else:
            _emit(
                f"ComfyUI health probe failed ({comfy_probe.get('error')}); recorded diagnostic"
            )

        _emit("RunPod bootstrap complete")
        return {
            "ok": True,
            "logs": logs,
            "artifacts": _artifact_summary(artifacts),
            "details": {
                "templates": templates_result.get("templates"),
                "quota": quota_result.get("quota"),
                "workspace_indexed": bool(workspace_manifest),
                "comfyui": comfy_probe,
            },
        }


__all__ = ["RunPodAdapter"]
