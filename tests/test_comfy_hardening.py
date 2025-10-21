from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from comfyvn.bridge.comfy_hardening import (
    CharacterLoRARegistry,
    HardenedBridgeError,
    HardenedBridgeUnavailable,
    HardenedComfyBridge,
)


class _FakeBridge:
    def __init__(self, response: Dict[str, Any]) -> None:
        self.response = response
        self.last_payload: Optional[Dict[str, Any]] = None

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.last_payload = payload
        return self.response


def _config_file(
    tmp_path: Path, *, enabled: bool, output_dir: Optional[Path] = None
) -> Path:
    payload: Dict[str, Any] = {"features": {"enable_comfy_bridge_hardening": enabled}}
    if output_dir:
        payload["integrations"] = {"comfyui_output_dir": str(output_dir)}
    path = tmp_path / "comfyvn.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_character_lora_registry_reads_entries(tmp_path: Path) -> None:
    base = tmp_path / "characters"
    entry = {
        "loras": [
            {"path": "models/loras/hero.safetensors", "weight": 0.75},
            {"path": "models/loras/style.safetensors", "weight": 1.25},
        ]
    }
    (base / "hero").mkdir(parents=True)
    (base / "hero" / "lora.json").write_text(json.dumps(entry), encoding="utf-8")

    registry = CharacterLoRARegistry(base_dir=base)
    items = registry.load("hero")

    assert len(items) == 2
    assert items[0].path.endswith("hero.safetensors")
    assert items[0].weight == pytest.approx(0.75)
    assert items[1].source == "hero"


def test_hardened_bridge_disabled_raises(tmp_path: Path) -> None:
    config = _config_file(tmp_path, enabled=False)
    bridge = HardenedComfyBridge(_FakeBridge({"ok": True}), config_paths=[config])

    with pytest.raises(HardenedBridgeError):
        bridge.submit({"workflow": {"graph": {"nodes": []}}})


def test_hardened_bridge_applies_overrides_and_reads_sidecar(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    (output_dir / "main").mkdir(parents=True)
    sidecar_path = output_dir / "main" / "meta.json"
    sidecar_payload = {"seed": 1234, "status": "ok"}
    sidecar_path.write_text(json.dumps(sidecar_payload), encoding="utf-8")

    response = {
        "ok": True,
        "prompt_id": "abc123",
        "workflow_id": "test_flow",
        "history": {"status": "completed"},
        "context": {"workflow_id": "test_flow"},
        "artifacts": [
            {
                "filename": "test.png",
                "subfolder": "main",
                "type": "image",
                "node_id": "image_node",
                "metadata": {},
            },
            {
                "filename": "meta.json",
                "subfolder": "main",
                "type": "json",
                "node_id": "meta_node",
                "metadata": {},
            },
        ],
    }

    characters_dir = tmp_path / "characters"
    (characters_dir / "hero").mkdir(parents=True)
    (characters_dir / "hero" / "lora.json").write_text(
        json.dumps(
            {"loras": [{"path": "models/loras/hero.safetensors", "weight": 0.8}]}
        ),
        encoding="utf-8",
    )

    config = _config_file(tmp_path, enabled=True, output_dir=output_dir)
    fake = _FakeBridge(response)
    bridge = HardenedComfyBridge(
        fake,
        config_paths=[config],
        lora_registry=CharacterLoRARegistry(base_dir=characters_dir),
    )

    workflow = {
        "workflow_id": "test_flow",
        "graph": {
            "nodes": [
                {
                    "id": 1,
                    "class_type": "KSampler",
                    "inputs": {
                        "seed": "{{seed}}",
                        "prompt": "{{prompt}}",
                        "loras": "{{loras}}",
                    },
                }
            ]
        },
    }

    payload = {
        "workflow": workflow,
        "prompt": "hero in the forest",
        "seed": 1234,
        "loras": [{"path": "models/loras/custom.safetensors", "weight": 1.1}],
        "character": "hero",
    }

    result = bridge.submit(payload)

    assert result["ok"] is True
    assert result["primary_artifact"]["path"] == str(output_dir / "main" / "test.png")
    assert result["sidecar_content"] == sidecar_payload
    assert "overrides" in result
    assert result["overrides"]["seed"] == 1234
    assert fake.last_payload is not None
    workflow_inputs = fake.last_payload["workflow"]["graph"]["nodes"][0]["inputs"]
    assert workflow_inputs["seed"] == 1234
    assert workflow_inputs["prompt"] == "hero in the forest"
    assert json.loads(workflow_inputs["loras"])[0]["path"].endswith(
        "custom.safetensors"
    )
    metadata = fake.last_payload["metadata"]
    assert metadata["characters"] == ["hero"]
    assert len(metadata["loras"]) == 2
    assert fake.last_payload["seeds"]["primary"] == 1234


def test_hardened_bridge_backend_error(tmp_path: Path) -> None:
    config = _config_file(tmp_path, enabled=True)
    fake = _FakeBridge({"ok": False, "error": "backend offline"})
    bridge = HardenedComfyBridge(fake, config_paths=[config])

    workflow = {"workflow_id": "wf", "graph": {"nodes": []}}

    with pytest.raises(HardenedBridgeUnavailable) as exc:
        bridge.submit({"workflow": workflow})

    assert exc.value.status_code == 503
