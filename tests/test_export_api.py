from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

import comfyvn.config.runtime_paths as runtime_paths
from comfyvn.config import feature_flags


def _prepare_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("COMFYVN_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("COMFYVN_RENPY_PROJECT_DIR", str(tmp_path / "renpy_project"))
    monkeypatch.setenv("COMFYVN_EXPORT_ROOT", str(tmp_path / "exports"))

    runtime_paths._runtime_roots.cache_clear()

    import sqlite3

    import comfyvn.core.db_manager as db_manager

    def _ensure_schema_stub(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT
                )
                """
            )
            conn.commit()

    monkeypatch.setattr(db_manager.DBManager, "ensure_schema", _ensure_schema_stub)

    import comfyvn.server.modules.export_api as export_api

    module = importlib.reload(export_api)
    module._renpy_project_root.cache_clear()
    module._exports_root.cache_clear()

    def _cleanup():
        runtime_paths._runtime_roots.cache_clear()
        module._renpy_project_root.cache_clear()
        module._exports_root.cache_clear()

    return _cleanup


def test_export_renpy_and_bundle(tmp_path, monkeypatch):
    cleanup = _prepare_workspace(tmp_path, monkeypatch)
    try:
        data_root = runtime_paths.data_dir()
        assert data_root.exists()

        scenes_dir = runtime_paths.data_dir("scenes")
        characters_dir = runtime_paths.data_dir("characters")
        timelines_dir = runtime_paths.data_dir("timelines")
        assets_dir = runtime_paths.data_dir("assets", "backgrounds")
        projects_dir = runtime_paths.data_dir("projects")

        scenes_dir.mkdir(parents=True, exist_ok=True)
        characters_dir.mkdir(parents=True, exist_ok=True)
        timelines_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)
        projects_dir.mkdir(parents=True, exist_ok=True)

        scene_intro = {
            "scene_id": "scene_intro",
            "title": "Intro",
            "lines": [
                {"type": "line", "speaker": "Hero", "text": "Welcome to ComfyVN!"},
                {
                    "type": "choice",
                    "prompt": "Continue?",
                    "options": [{"text": "Yes", "goto": "scene_outro"}],
                },
            ],
        }
        scene_outro = {
            "scene_id": "scene_outro",
            "title": "Outro",
            "dialogue": [
                {"type": "line", "speaker": None, "text": "Thanks for playing."}
            ],
        }

        (scenes_dir / "scene_intro.json").write_text(
            json.dumps(scene_intro, indent=2), encoding="utf-8"
        )
        (scenes_dir / "scene_outro.json").write_text(
            json.dumps(scene_outro, indent=2), encoding="utf-8"
        )

        character_payload = {
            "character_id": "hero",
            "name": "Hero",
            "meta": {"role": "protagonist"},
        }
        (characters_dir / "hero.json").write_text(
            json.dumps(character_payload, indent=2), encoding="utf-8"
        )

        asset_path = assets_dir / "bg1.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(b"fake-png-data")

        timeline_payload = {
            "timeline_id": "main",
            "title": "Main Timeline",
            "scene_order": [{"scene_id": "scene_intro"}, {"scene_id": "scene_outro"}],
            "project_id": "demo",
        }
        (timelines_dir / "main.json").write_text(
            json.dumps(timeline_payload, indent=2), encoding="utf-8"
        )

        project_payload = {
            "name": "demo",
            "title": "Demo Project",
            "scenes": ["scene_intro", "scene_outro"],
            "characters": ["hero"],
            "assets": ["backgrounds/bg1.png"],
            "licenses": [{"name": "CC-BY", "scope": "backgrounds"}],
        }
        (projects_dir / "demo.json").write_text(
            json.dumps(project_payload, indent=2), encoding="utf-8"
        )

        original_is_enabled = feature_flags.is_enabled

        def _patched_is_enabled(
            name: str, *, default: bool | None = None, refresh: bool = False
        ) -> bool:
            if name == "enable_export_bundle":
                return True
            return original_is_enabled(name, default=default, refresh=refresh)

        monkeypatch.setattr(feature_flags, "is_enabled", _patched_is_enabled)

        from comfyvn.core import policy_gate as policy_gate_module

        def _allow_action(action: str, *_args, **_kwargs) -> dict:
            return {"allow": True, "requires_ack": False, "warnings": []}

        monkeypatch.setattr(
            policy_gate_module.policy_gate, "evaluate_action", _allow_action
        )

        from comfyvn.server.app import create_app

        client = TestClient(create_app())

        renpy_resp = client.post(
            "/api/export/renpy", params={"timeline_id": "main", "project_id": "demo"}
        )
        assert renpy_resp.status_code == 200
        data = renpy_resp.json()
        assert data["ok"] is True

        script_path = Path(data["script"])
        assert script_path.exists()
        script_text = script_path.read_text(encoding="utf-8")
        assert "label start:" in script_text
        assert "call scene_intro" in script_text
        assert "label scene_outro:" in script_text

        bundle_resp = client.post(
            "/api/export/bundle", params={"project_id": "demo", "timeline_id": "main"}
        )
        assert bundle_resp.status_code == 200
        bundle_data = bundle_resp.json()
        assert bundle_data["ok"] is True

        bundle_path = Path(bundle_data["bundle"])
        assert bundle_path.exists()

        with zipfile.ZipFile(bundle_path, "r") as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            assert "provenance.json" in names
            assert "timelines/main.json" in names
            assert "scenes/scene_intro.json" in names
            assert "scenes/scene_outro.json" in names
            assert "characters/hero.json" in names
            assert "assets/backgrounds/bg1.png" in names
            assert "renpy_project/game/script.rpy" in names

            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            assert manifest["id"] == "demo"
            assert manifest["timeline_id"] == "main"

            exported_script = archive.read("renpy_project/game/script.rpy").decode(
                "utf-8"
            )
            assert "label scene_intro:" in exported_script
            assert '"Hero" "Welcome to ComfyVN!"' in exported_script

            provenance = json.loads(archive.read("provenance.json").decode("utf-8"))
            assert provenance["timeline"]["id"] == "main"
            assert "scene_intro" in provenance["scenes"]
            assert provenance["renpy_project"]["script"].endswith("script.rpy")

        public_renpy_resp = client.post(
            "/export/renpy",
            params={
                "project_id": "demo",
                "timeline_id": "main",
                "force": True,
            },
        )
        assert public_renpy_resp.status_code == 200
        public_data = public_renpy_resp.json()
        assert public_data["ok"] is True
        assert public_data["dry_run"] is False
        export_path = Path(public_data["path"])
        assert export_path.exists()
        assert Path(public_data["script"]).exists()
        assert Path(public_data["provenance_json"]).exists()
        assert public_data["asset_validation"]["matches"] is True

        public_bundle_resp = client.post(
            "/export/bundle",
            params={
                "project_id": "demo",
                "timeline_id": "main",
            },
        )
        assert public_bundle_resp.status_code == 200
        public_bundle = public_bundle_resp.json()
        assert public_bundle["ok"] is True
        bundle_zip = Path(public_bundle["path"])
        assert bundle_zip.exists()
        assert public_bundle["asset_validation"]["matches"] is True
        with zipfile.ZipFile(bundle_zip, "r") as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            assert "provenance.json" in names
    finally:
        cleanup()
