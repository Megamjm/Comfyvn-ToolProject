from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import pytest

from comfyvn.bridge.comfy import ComfyBridgeError
from comfyvn.bridge.comfy_stream import PreviewCollector
from comfyvn.core.comfy_bridge import ComfyBridge


def test_preview_collector_writes_manifest(tmp_path: Path):
    content = b"fake-image"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/view")
        return httpx.Response(200, content=content)

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            collector = PreviewCollector(tmp_path / "previews")
            record = {
                "outputs": {
                    "node1": [
                        {
                            "filename": "preview.png",
                            "type": "preview",
                            "subfolder": "",
                        }
                    ]
                }
            }
            await collector.collect(
                client, record, prompt_id="prompt", base_url="http://unit"
            )
            collector.finalize(None)

    asyncio.run(_run())

    manifest_path = tmp_path / "previews" / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["previews"][0]["filename"] == "preview.png"


class _StubResult:
    def __init__(self) -> None:
        self._payload = {"prompt_id": "p123", "workflow_id": "wf"}

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._payload)


class _StubBridge:
    def __init__(self) -> None:
        self.base_url = "http://example"
        self.calls = 0
        self.preview_dirs: list[Optional[Path]] = []

    async def run_workflow(
        self,
        workflow: Dict[str, Any],
        *,
        context,
        poll_interval: float,
        timeout: float,
        download_dir: Optional[Path] = None,
        preview_dir: Optional[Path] = None,
        preview_callback=None,
    ):
        self.calls += 1
        self.preview_dirs.append(preview_dir)
        if self.calls == 1:
            raise ComfyBridgeError("fail once")
        return _StubResult()

    async def download_artifacts(self, result: _StubResult, target: Path):
        return []


def test_comfy_bridge_resume_and_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bridge = ComfyBridge()
    stub = _StubBridge()
    bridge._bridge = stub  # type: ignore[attr-defined]

    payload = {
        "workflow": {"nodes": []},
        "preview_stream": True,
        "resume_on_error": True,
        "resume_attempts": 2,
        "preview_dir": str(tmp_path / "previews"),
    }

    result = asyncio.run(bridge.submit_async(payload))

    assert result["ok"] is True
    resume = result.get("resume") or {}
    assert resume.get("recovered") is True
    assert len(resume.get("attempts") or []) == 1
    assert stub.calls == 2
    assert any(preview is not None for preview in stub.preview_dirs)
