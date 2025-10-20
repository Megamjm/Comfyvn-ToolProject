import pathlib

import pytest

from comfyvn.assets_manifest import build_manifest


def _create_png(path: pathlib.Path, size=(16, 16)) -> bool:
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return False
    img = Image.new("RGBA", size, (255, 0, 0, 255))  # type: ignore[attr-defined]
    img.save(path)
    return True


@pytest.mark.parametrize("extension", ["png", "webp"])
def test_manifest_builds_and_groups(tmp_path: pathlib.Path, extension: str) -> None:
    assets_root = tmp_path / "assets"
    (assets_root / "characters" / "Ari").mkdir(parents=True)
    (assets_root / "bg").mkdir(parents=True)

    creator_ok = _create_png(assets_root / "characters" / "Ari" / f"happy.{extension}")
    creator_ok = creator_ok and _create_png(assets_root / "bg" / f"room.{extension}")
    if not creator_ok:
        pytest.skip("Pillow not installed")

    manifest = build_manifest(str(assets_root))
    assert manifest["count"] == 2
    assert "Ari" in manifest["by_character"]
    assert "room" in manifest["by_background"]
