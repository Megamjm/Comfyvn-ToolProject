from __future__ import annotations

import zipfile
from pathlib import Path

from comfyvn.server.core.manga_importer import MangaImportError, import_manga_archive


def _make_manga_archive(tmp_path: Path) -> Path:
    archive_path = tmp_path / "demo.cbz"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("chapter1/page1.png", b"fake-image-data")
        archive.writestr("chapter1/page1.txt", "Alice: Hello!\nBob: Hi Alice!")
        archive.writestr("chapter1/page2.png", b"more-data")
    return archive_path


def test_import_manga_archive(tmp_path: Path):
    archive_path = _make_manga_archive(tmp_path)
    data_root = tmp_path / "data_root"

    summary = import_manga_archive(archive_path, data_root=data_root, translation_lang="en")

    assert summary["scenes"]
    assert summary["timelines"]
    assert summary["assets"]
    assert summary["summary_path"]
    assert Path(summary["summary_path"]).exists()
    assert summary["translation"]["bundle_path"]
    assert summary["panels"]
    # Assets copied under assets/manga/<import_id>/...
    asset_rel = summary["assets"][0]
    assert (data_root / "assets" / asset_rel).exists()
    # Scene JSON persisted
    scene_id = summary["scenes"][0]
    assert (data_root / "scenes" / f"{scene_id}.json").exists()
    timeline_id = summary["timelines"][0]
    assert (data_root / "timelines" / f"{timeline_id}.json").exists()
    assert summary["advisories"], "missing license metadata should emit advisory issues"


def test_import_manga_archive_with_license_hint(tmp_path: Path):
    archive_path = _make_manga_archive(tmp_path)
    data_root = tmp_path / "data_root_license"

    summary = import_manga_archive(
        archive_path,
        data_root=data_root,
        translation_enabled=False,
        license_hint="CC-BY",
    )

    assert summary["licenses"]
    assert summary["licenses"][0]["name"] == "CC-BY"
    assert summary["advisories"] == [], "open license hint should suppress advisory warnings"


def test_import_manga_archive_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.cbz"
    try:
        import_manga_archive(missing)
        assert False, "expected MangaImportError"
    except MangaImportError:
        pass
