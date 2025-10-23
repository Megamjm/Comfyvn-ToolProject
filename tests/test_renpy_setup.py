from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Optional

import comfyvn.importers.renpy_setup as renpy_setup


class _DummyClient:
    def close(self) -> None:
        pass


def test_ensure_renpy_sdk_reuses_existing_install(tmp_path: Path):
    install_root = tmp_path / "tools"
    existing = install_root / "renpy-9.9.9-sdk"
    existing.mkdir(parents=True)
    (existing / "renpy.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    result = renpy_setup.ensure_renpy_sdk(
        version="9.9.9",
        install_root=install_root,
        cache_dir=tmp_path / "cache",
    )
    assert result == existing


def test_ensure_renpy_sdk_installs_via_stubbed_archive(tmp_path: Path, monkeypatch):
    archive = tmp_path / "renpy-archive.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("renpy-9.9.9-sdk/renpy.sh", "#!/bin/sh\n")
        zf.writestr("renpy-9.9.9-sdk/README.txt", "stub")

    install_root = tmp_path / "install"
    client = _DummyClient()

    monkeypatch.setattr(renpy_setup, "discover_latest_version", lambda _: "9.9.9")

    def _fake_download(
        version: str, _client, *, cache_dir: Optional[Path] = None
    ) -> Path:
        target_root = Path(cache_dir) if cache_dir else tmp_path
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / archive.name
        shutil.copy2(archive, target)
        return target

    monkeypatch.setattr(renpy_setup, "_download_archive", _fake_download)

    result = renpy_setup.ensure_renpy_sdk(
        install_root=install_root,
        client=client,
        cache_dir=tmp_path / "cache",
    )
    assert result.exists()
    assert (result / "renpy.sh").exists()
    metadata = (result / "comfyvn.install.json").read_text(encoding="utf-8")
    assert '"version": "9.9.9"' in metadata
