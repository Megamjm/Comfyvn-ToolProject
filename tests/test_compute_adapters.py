from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any, Dict

import httpx
import pytest

from comfyvn.bridge.remote import RemoteCapabilityReport
from comfyvn.compute.providers_runpod import RunPodAdapter
from comfyvn.compute.providers_unraid import UnraidAdapter


def test_runpod_adapter_fetch_templates():
    provider = {"id": "runpod", "base_url": "https://api.runpod.io/v2"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pod-templates"):
            payload = {
                "data": [
                    {
                        "id": "tmpl-1",
                        "name": "A10 Starter",
                        "gpu": "A10G",
                        "hourlyPrice": 0.49,
                    }
                ]
            }
            return httpx.Response(200, json=payload)
        raise AssertionError(f"Unexpected path {request.url}")

    async def _run() -> Dict[str, Any]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = RunPodAdapter.from_provider(provider)
            adapter.client = client
            return await adapter.fetch_templates()

    result = asyncio.run(_run())

    assert result["ok"] is True
    templates = result["templates"]
    assert len(templates) == 1
    assert templates[0]["id"] == "tmpl-1"
    assert templates[0]["gpu"] == "A10G"


def test_runpod_adapter_quota_failure():
    provider = {"id": "runpod", "base_url": "https://api.runpod.io/v2"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    async def _run() -> Dict[str, Any]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            adapter = RunPodAdapter.from_provider(provider)
            adapter.client = client
            return await adapter.fetch_quota()

    result = asyncio.run(_run())

    assert result["ok"] is False
    assert result["status_code"] == 404


class _FakeBridge:
    def __init__(self, outputs: Dict[str, Any]) -> None:
        self.outputs = outputs
        self.run_calls: list[str] = []

    def run(
        self, command: str, *, check: bool = False, timeout: float = 120.0
    ) -> subprocess.CompletedProcess[str]:
        self.run_calls.append(command)
        stdout = ""
        if "docker images" in command:
            stdout = json.dumps(
                {"Repository": "comfyui/custom", "Tag": "latest", "Size": "1GB"}
            )
        elif "python3 - <<" in command:
            stdout = json.dumps({"dirs": ["bootstrap"]})
        return subprocess.CompletedProcess(command, 0, stdout, "")

    def capability_probe(self) -> RemoteCapabilityReport:
        return RemoteCapabilityReport(ok=True, summary="ok", details=self.outputs)


def test_unraid_bootstrap(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "graph.json").write_text("{}", encoding="utf-8")

    fake_bridge = _FakeBridge({"gpu": []})
    provider = {
        "id": "unraid",
        "base_url": "http://127.0.0.1:8188",
        "config": {"ssh": {"host": "unraid.local", "user": "root"}},
    }
    adapter = UnraidAdapter.from_provider(
        provider,
        bridge_factory=lambda *args, **kwargs: fake_bridge,
    )

    async def _run() -> Dict[str, Any]:
        return await adapter.bootstrap(output_dir=tmp_path, workspace=workspace)

    result = asyncio.run(_run())
    assert result["ok"] is True
    artifacts = result["artifacts"]
    assert any("unraid_bootstrap_report.json" in path for path in artifacts)
    assert any("workspace_manifest.json" in path for path in artifacts)
    assert any("bootstrap.log" in path for path in artifacts)
