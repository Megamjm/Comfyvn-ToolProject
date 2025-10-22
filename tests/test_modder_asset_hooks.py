from __future__ import annotations

from pathlib import Path

from comfyvn.core import modder_hooks
from comfyvn.studio.core.asset_registry import AssetRegistry


def test_modder_asset_hooks_emit_expected_events(tmp_path):
    db_path = tmp_path / "assets.db"
    assets_root = tmp_path / "assets"
    thumbs_root = tmp_path / "thumbs"
    meta_root = tmp_path / "meta"

    registry = AssetRegistry(
        db_path=db_path,
        project_id="test",
        assets_root=assets_root,
        thumb_root=thumbs_root,
        meta_root=meta_root,
    )

    recorded: list[tuple[str, dict]] = []

    def _listener(event: str, payload: dict) -> None:
        recorded.append((event, payload))

    hook_names = (
        "on_asset_saved",
        "on_asset_registered",
        "on_asset_meta_updated",
        "on_asset_removed",
        "on_asset_sidecar_written",
    )
    modder_hooks.register_listener(_listener, hook_names)
    try:
        source = tmp_path / "sample.txt"
        source.write_text("hello world", encoding="utf-8")

        registered = registry.register_file(source, "generic", copy=True)
        uid = registered["uid"]
        assert uid

        registry.update_asset_meta(uid, {"tags": ["debug"]})
        registry.remove_asset(uid, delete_files=False)
    finally:
        modder_hooks.unregister_listener(_listener, hook_names)

    events_by_name = {}
    for name, payload in recorded:
        events_by_name.setdefault(name, []).append(payload)

    assert "on_asset_saved" in events_by_name
    assert "on_asset_registered" in events_by_name
    assert "on_asset_meta_updated" in events_by_name
    assert "on_asset_removed" in events_by_name
    assert "on_asset_sidecar_written" in events_by_name

    saved_payload = events_by_name["on_asset_saved"][-1]
    assert saved_payload["uid"] == uid
    assert saved_payload["path"].endswith(".txt")
    assert saved_payload.get("hook_event") == "asset_registered"

    registered_payload = events_by_name["on_asset_registered"][-1]
    assert registered_payload["uid"] == uid
    assert registered_payload["path"].endswith(".txt")
    assert registered_payload.get("hook_event") == "asset_registered"

    updated_payload = events_by_name["on_asset_meta_updated"][-1]
    assert updated_payload["uid"] == uid
    assert updated_payload["meta"]["tags"] == ["debug"]
    assert updated_payload.get("hook_event") == "asset_meta_updated"

    removed_payload = events_by_name["on_asset_removed"][-1]
    assert removed_payload["uid"] == uid
    assert removed_payload["path"].endswith(".txt")
    assert removed_payload.get("hook_event") == "asset_removed"

    sidecar_payload = events_by_name["on_asset_sidecar_written"][-1]
    assert sidecar_payload["uid"] == uid
    assert Path(sidecar_payload["sidecar"]).suffix.endswith(".json")
    assert sidecar_payload.get("hook_event") == "asset_sidecar_written"
