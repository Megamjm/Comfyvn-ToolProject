from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

from comfyvn.core import modder_hooks
from comfyvn.studio.core.asset_registry import AssetRegistry


def _make_registry(tmp_path: Path) -> AssetRegistry:
    db_path = tmp_path / "assets.sqlite"
    assets_root = tmp_path / "assets"
    thumbs_root = tmp_path / "thumbs"
    return AssetRegistry(
        db_path=db_path,
        assets_root=assets_root,
        thumb_root=thumbs_root,
        meta_root=False,
        project_id="test",
    )


def test_list_assets_supports_hash_tags_and_text_filters(tmp_path):
    registry = _make_registry(tmp_path)

    first_src = tmp_path / "first.txt"
    first_src.write_text("alpha-file", encoding="utf-8")
    first_asset = registry.register_file(
        first_src,
        "documents",
        metadata={"tags": ["alpha", "hero"], "notes": "The first sample asset."},
    )

    second_src = tmp_path / "second.txt"
    second_src.write_text("beta-file", encoding="utf-8")
    second_asset = registry.register_file(
        second_src,
        "documents",
        metadata={"tags": ["beta", "npc"], "notes": "Second SAMPLE asset for tests."},
    )

    all_assets = registry.list_assets()
    assert {asset["uid"] for asset in all_assets} == {
        first_asset["uid"],
        second_asset["uid"],
    }

    hash_filtered = registry.list_assets(hash_value=first_asset["hash"])
    assert [asset["uid"] for asset in hash_filtered] == [first_asset["uid"]]

    tag_filtered = registry.list_assets(tags=["alpha"])
    assert [asset["uid"] for asset in tag_filtered] == [first_asset["uid"]]

    multi_tag_filtered = registry.list_assets(tags=["alpha", "hero"])
    assert [asset["uid"] for asset in multi_tag_filtered] == [first_asset["uid"]]

    case_insensitive = registry.list_assets(tags=["ALPHA"])
    assert [asset["uid"] for asset in case_insensitive] == [first_asset["uid"]]

    missing_tag_filtered = registry.list_assets(tags=["alpha", "missing"])
    assert missing_tag_filtered == []

    search_notes = registry.list_assets(text="sample")
    assert {asset["uid"] for asset in search_notes} == {
        first_asset["uid"],
        second_asset["uid"],
    }

    search_path = registry.list_assets(text="second.txt")
    assert [asset["uid"] for asset in search_path] == [second_asset["uid"]]

    AssetRegistry.wait_for_thumbnails(timeout=5.0)


def test_asset_modder_hooks_emit_for_registry_events(tmp_path):
    registry = _make_registry(tmp_path)
    events: dict[str, list[dict[str, object]]] = defaultdict(list)

    def listener(event: str, payload: dict[str, object]) -> None:
        events[event].append(payload)

    interested = [
        "on_asset_registered",
        "on_asset_saved",
        "on_asset_meta_updated",
        "on_asset_sidecar_written",
        "on_asset_removed",
    ]
    modder_hooks.register_listener(listener, events=interested)
    registered = None
    try:
        source = tmp_path / "asset.bin"
        source.write_bytes(b"payload-1")

        registered = registry.register_file(
            source,
            "binary",
            metadata={"tags": ["hook-test"], "notes": "hook baseline"},
        )

        registry.update_asset_meta(registered["uid"], {"tags": ["hook-test", "v2"]})
        registry.ensure_sidecar(registered["uid"], overwrite=True)
        registry.remove_asset(registered["uid"], delete_files=False)
    finally:
        modder_hooks.unregister_listener(listener, events=interested)

    AssetRegistry.wait_for_thumbnails(timeout=5.0)

    # Event buckets should exist for each hook type.
    for name in interested:
        assert name in events, f"expected modder hook {name} to fire"

    assert registered is not None
    reg_event = events["on_asset_registered"][0]
    assert reg_event["uid"] == registered["uid"]
    assert reg_event["hook_event"] == "asset_registered"

    meta_event = events["on_asset_meta_updated"][0]
    assert meta_event["uid"] == registered["uid"]
    assert meta_event["meta"]["tags"] == ["hook-test", "v2"]  # type: ignore[index]

    removed_event = events["on_asset_removed"][0]
    assert removed_event["uid"] == registered["uid"]


def test_register_file_deduplicates_by_hash(tmp_path):
    registry = _make_registry(tmp_path)

    source = tmp_path / "duplicate.bin"
    source.write_bytes(b"registry-dedupe-test")

    first = registry.register_file(
        source,
        "binary",
        metadata={"tags": ["first"], "origin": "dedupe"},
    )
    second = registry.register_file(
        source,
        "binary",
        metadata={"tags": ["second"], "origin": "dedupe"},
    )

    assert first["uid"] == second["uid"]
    assets = registry.list_assets()
    assert len(assets) == 1
    stored_meta = assets[0]["meta"]
    assert isinstance(stored_meta, dict)
    assert set(stored_meta.get("tags", [])) == {"first", "second"}
    assert stored_meta.get("origin") == "dedupe"


@pytest.mark.skipif(Image is None, reason="Pillow required for thumbnail generation")
def test_image_thumbnail_generates_multiple_sizes(tmp_path):
    registry = _make_registry(tmp_path)

    source = tmp_path / "sample.png"
    img = Image.new("RGB", (32, 32), color="blue")  # type: ignore[attr-defined]
    img.save(source)  # type: ignore[attr-defined]

    asset = registry.register_file(source, "images")
    AssetRegistry.wait_for_thumbnails(timeout=10.0)

    meta = asset.get("meta") or {}
    preview = meta.get("preview") if isinstance(meta, dict) else None
    assert isinstance(preview, dict)
    paths = preview.get("paths") or {}
    assert set(paths.keys()) == {"256", "512"}
    thumb_root = registry.THUMB_ROOT
    for rel in paths.values():
        thumb_path = thumb_root / Path(rel).name
        assert thumb_path.exists(), f"expected thumbnail at {thumb_path}"
