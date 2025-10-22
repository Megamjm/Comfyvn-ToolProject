from __future__ import annotations

import json
from pathlib import Path

from comfyvn.bridge.comfy_hardening import LoRAEntry
from comfyvn.pov.render_pipeline import (
    POVRenderCache,
    POVRenderPipeline,
)
from comfyvn.studio.core.asset_registry import AssetRegistry


class _FakeBridge:
    def __init__(self, root: Path) -> None:
        self.enabled = True
        self._root = root
        self._counter = 0

    def reload(self) -> None:
        return None

    def character_loras(self, characters):
        return [LoRAEntry(path="models/lora/test.safetensors", weight=0.85)]

    def submit(self, payload):
        self._counter += 1
        artifact_path = self._root / f"artifact_{self._counter}.png"
        artifact_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        sidecar_path = self._root / f"artifact_{self._counter}.json"
        sidecar_path.write_text(
            json.dumps({"counter": self._counter}), encoding="utf-8"
        )
        return {
            "ok": True,
            "workflow_id": payload.get("workflow_id"),
            "prompt_id": f"prompt-{self._counter}",
            "primary_artifact": {"path": str(artifact_path)},
            "sidecar": {"path": str(sidecar_path)},
            "sidecar_content": {"counter": self._counter},
            "overrides": {
                "loras": [
                    {
                        "path": "models/lora/test.safetensors",
                        "weight": 0.85,
                    }
                ],
                "seed": 42 + self._counter,
            },
        }


def _pipeline(tmp_path: Path) -> tuple[POVRenderPipeline, _FakeBridge]:
    bridge = _FakeBridge(tmp_path / "bridge")
    (tmp_path / "bridge").mkdir(parents=True, exist_ok=True)
    registry = AssetRegistry(
        db_path=tmp_path / "registry.sqlite",
        assets_root=tmp_path / "assets",
        thumb_root=tmp_path / "thumbs",
        meta_root=tmp_path / "assets" / "_meta",
    )
    cache = POVRenderCache(path=tmp_path / "cache.json")
    pipeline = POVRenderPipeline(
        bridge=bridge,
        registry=registry,
        render_root=tmp_path / "renders",
        cache=cache,
    )
    return pipeline, bridge


def test_pipeline_renders_and_caches(tmp_path: Path) -> None:
    pipeline, bridge = _pipeline(tmp_path)

    results = pipeline.ensure_poses("alice", style="hero", poses=["neutral"])
    assert len(results) == 1
    first = results[0]
    assert first["cached"] is False
    assert Path(first["asset_path"]).exists()
    assert first["loras"][0]["path"].endswith("test.safetensors")
    assert bridge._counter == 1

    cached = pipeline.ensure_poses("alice", style="hero", poses=["neutral"])
    cached_first = cached[0]
    assert cached_first["cached"] is True
    assert bridge._counter == 1

    forced = pipeline.ensure_poses("alice", style="hero", poses=["neutral"], force=True)
    assert forced[0]["cached"] is False
    assert bridge._counter == 2
