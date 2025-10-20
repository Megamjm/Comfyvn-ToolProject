# tests/test_scene_bundle.py
# [S2 Scene Bundle Export — ComfyVN Architect | 2025-10-20 | chat: S2]
import json, pathlib
from comfyvn.scene_bundle import build_bundle

def test_build_bundle_minimal(tmp_path):
    raw = {
        "id": "scene-xyz",
        "title": "Test Title",
        "dialogue": [
            {"type":"line","speaker":"Ari","text":"Hello there! [[bg:room]]","emotion":None},
            {"type":"line","speaker":"Ben","text":"Hey Ari?", "emotion":None},
            {"type":"line","speaker":"Ari","text":"All good.", "emotion":"neutral"}
        ]
    }
    # Fake manifest to simulate existing assets
    manifest = {
        "by_character": {
            "Ari": {"neutral":"characters/Ari/neutral.png", "excited":"characters/Ari/excited.png"},
            "Ben": {"neutral":"characters/Ben/neutral.png"}
        },
        "by_background": {"room":"bg/room.png"}
    }
    b = build_bundle(raw, manifest)
    names = [c["name"] for c in b["characters"]]
    assert "Ari" in names and "Ben" in names
    assert any(x for x in b["dialogue"] if x["type"]=="scene" and x.get("target_bg")=="room")
    assert b["assets"]["backgrounds"].get("room") == "bg/room.png"
