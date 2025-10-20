from __future__ import annotations

import json
from pathlib import Path

from comfyvn.importers.renpy import RenpyImporter
from comfyvn.importers.kirikiri import KiriKiriImporter
from comfyvn.core.normalizer import normalize_tree


def _write_file(path: Path, content: bytes | str = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def test_renpy_detection(tmp_path: Path, monkeypatch):
    game_dir = tmp_path / "game"
    _write_file(game_dir / "script.rpy", "label start: pass")
    _write_file(game_dir / "images.rpa", b"dummy")

    fake_sdk = tmp_path / "renpy-sdk"
    fake_sdk.mkdir()
    _write_file(fake_sdk / "renpy.sh", "#!/bin/sh\n")
    monkeypatch.setattr("comfyvn.importers.renpy.ensure_renpy_sdk", lambda: fake_sdk)
    monkeypatch.setattr("comfyvn.importers.renpy.get_renpy_executable", lambda _: fake_sdk / "renpy.sh")

    importer = RenpyImporter()
    det = importer.detect(tmp_path)
    assert det.confidence > 0.6
    pack_path = importer.import_pack(tmp_path, tmp_path / "output")
    manifest = json.loads((pack_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["engine"] == importer.label
    assert manifest["schema"] == "comfyvn-pack@1"
    assert manifest["sources"]["renpy_home"] == str(fake_sdk)
    assert manifest["sources"]["renpy_executable"].endswith("renpy.sh")


def test_kirikiri_detection(tmp_path: Path):
    _write_file(tmp_path / "data.xp3", b"dummy")
    _write_file(tmp_path / "scenario.ks", "[r]\nHello")

    importer = KiriKiriImporter()
    det = importer.detect(tmp_path)
    assert det.confidence > 0.4

    pack_path = importer.import_pack(tmp_path, tmp_path / "out")
    assert (pack_path / "manifest.json").exists()


def test_normalizer_categorises_assets(tmp_path: Path):
    src = tmp_path / "src"
    _write_file(src / "bg" / "school.png", b"fake")
    _write_file(src / "voice" / "line1.ogg", b"fake")
    _write_file(src / "scenario.ks", "*start")

    pack = normalize_tree(src, tmp_path / "dest", engine="TestEngine")
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["assets"]["bg"]
    assert manifest["assets"]["audio"]["voice"]
    assert manifest["text"]
