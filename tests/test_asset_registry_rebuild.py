from __future__ import annotations

from pathlib import Path

import pytest

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

from comfyvn.registry.rebuild import rebuild_from_disk
from comfyvn.studio.core.asset_registry import AssetRegistry


@pytest.mark.skipif(Image is None, reason="Pillow required for thumbnail generation")
def test_rebuild_from_disk_discovers_manual_assets(tmp_path: Path):
    assets_root = tmp_path / "assets"
    manual_dir = assets_root / "images"
    manual_dir.mkdir(parents=True, exist_ok=True)
    manual_asset = manual_dir / "manual.png"

    image = Image.new("RGB", (48, 48), color="green")  # type: ignore[attr-defined]
    image.save(manual_asset)  # type: ignore[attr-defined]

    db_path = tmp_path / "registry.sqlite"
    thumbs_root = tmp_path / "thumbs"

    summary = rebuild_from_disk(
        assets_root=assets_root,
        db_path=db_path,
        thumbs_root=thumbs_root,
        project_id="test",
        remove_stale=True,
        wait_for_thumbs=True,
    )

    assert summary.processed == 1
    assert summary.removed == 0

    registry = AssetRegistry(
        db_path=db_path,
        assets_root=assets_root,
        thumb_root=thumbs_root,
        project_id="test",
        meta_root=False,
    )
    assets = registry.list_assets()
    assert len(assets) == 1
    asset = assets[0]
    meta = asset.get("meta") or {}
    preview = meta.get("preview") if isinstance(meta, dict) else None
    assert isinstance(preview, dict)
    paths = preview.get("paths") or {}
    assert set(paths.keys()) == {"256", "512"}
    for rel in paths.values():
        thumb_path = thumbs_root / Path(rel).name
        assert thumb_path.exists(), f"expected thumbnail at {thumb_path}"
