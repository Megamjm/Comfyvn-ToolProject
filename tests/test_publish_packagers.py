from __future__ import annotations

import json
from pathlib import Path

from comfyvn.exporters import itch_packager, steam_packager
from comfyvn.exporters.publish_common import PackageOptions
from comfyvn.exporters.renpy_orchestrator import ExportResult


def _export_result(tmp_path: Path, *, with_game: bool = True) -> ExportResult:
    output_dir = tmp_path / ("game_output" if with_game else "dry_output")
    game_dir = output_dir / "game"
    if with_game:
        (game_dir / "assets").mkdir(parents=True, exist_ok=True)
        (game_dir / "readme.txt").write_text("demo content", encoding="utf-8")
    export_manifest = output_dir / "export_manifest.json"
    export_manifest.parent.mkdir(parents=True, exist_ok=True)
    export_manifest.write_text("{}", encoding="utf-8")
    script_path = game_dir / "script.rpy"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("label start:\n    pass\n", encoding="utf-8")
    manifest_payload = {
        "project": {"id": "demo", "title": "Demo", "source": "project.json"},
        "timeline": {"id": "main", "title": "Main", "source": "timeline.json"},
        "generated_at": "2025-01-01T00:00:00Z",
        "output_dir": output_dir.as_posix(),
        "script": {"path": "game/script.rpy", "labels": []},
        "pov": {"mode": "disabled", "routes": []},
        "worlds": {"mode": "none", "active": None, "worlds": []},
        "assets": {"backgrounds": [], "portraits": []},
        "missing_assets": {"backgrounds": [], "portraits": []},
        "gate": {},
    }
    return ExportResult(
        ok=True,
        project_id="demo",
        timeline_id="main",
        gate={},
        rating_gate={},
        output_dir=output_dir,
        generated_at="2025-01-01T00:00:00Z",
        script_path=script_path,
        scene_files={},
        label_map=[],
        backgrounds={},
        portraits={},
        manifest_path=export_manifest,
        manifest_payload=manifest_payload,
        missing_backgrounds=set(),
        missing_portraits=[],
    )


def test_steam_package_reproducible(tmp_path: Path) -> None:
    export_result = _export_result(tmp_path)
    publish_root = tmp_path / "publish"
    options = PackageOptions(
        label="Demo Build",
        version="0.1.0",
        platforms=("windows", "linux"),
        publish_root=publish_root,
        dry_run=False,
    )

    first = steam_packager.package(export_result, options)
    assert first.checksum
    assert first.archive_path and first.archive_path.exists()
    assert first.manifest_path.exists()
    assert first.license_manifest_path.exists()
    for sidecar in first.provenance_sidecars.values():
        if sidecar:
            assert Path(sidecar).exists()

    second = steam_packager.package(export_result, options)
    assert second.checksum == first.checksum
    assert all(entry["status"] != "modified" for entry in _normalised_diffs(second))


def test_itch_package_dry_run(tmp_path: Path) -> None:
    export_result = _export_result(tmp_path, with_game=False)
    publish_root = tmp_path / "publish_dry"
    options = PackageOptions(
        label="Dry Run",
        version="0.0.1",
        platforms=("windows",),
        publish_root=publish_root,
        dry_run=True,
    )

    result = itch_packager.package(export_result, options)
    assert result.dry_run is True
    assert result.checksum is None
    assert any(entry["status"] == "new" for entry in _normalised_diffs(result))
    assert not result.provenance_sidecars


def _normalised_diffs(result) -> list[dict]:
    payloads: list[dict] = []
    for entry in result.diffs:
        data: dict = {"status": entry.status}
        if entry.detail:
            try:
                detail = json.loads(entry.detail)
                if isinstance(detail, dict):
                    data.update(detail)
                else:
                    data["detail"] = entry.detail
            except json.JSONDecodeError:
                data["detail"] = entry.detail
        payloads.append(data)
    return payloads
