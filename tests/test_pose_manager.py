from __future__ import annotations

from comfyvn.assets.pose_manager import PoseManager
from comfyvn.studio.core import AssetRegistry


def test_pose_manager_registers_and_lists_poses(tmp_path):
    assets_root = tmp_path / "assets"
    thumbs_root = tmp_path / "thumbs"
    meta_root = tmp_path / "meta"
    db_path = tmp_path / "db.sqlite"

    registry = AssetRegistry(
        db_path=db_path,
        assets_root=assets_root,
        thumb_root=thumbs_root,
        meta_root=meta_root,
    )
    pose_dir = assets_root / "poses"
    manager = PoseManager(poses_dir=pose_dir, registry=registry)

    pose_payload = {"pose_id": "hero_stand", "x": 42, "y": -7}
    result = manager.add_pose("hero_stand", pose_payload, metadata={"origin": "test-suite"})
    assert result["uid"]
    assert result["sidecar"].endswith(".json.asset.json")

    pose_file = pose_dir / "hero_stand.json"
    assert pose_file.exists()
    sidecar_path = pose_file.parent / f"{pose_file.name}.asset.json"
    assert sidecar_path.exists()
    assert str(pose_file) in manager.list()

    listed = manager.list_poses()
    pose_ids = {entry["id"] for entry in listed}
    assert "hero_stand" in pose_ids

    loaded = manager.get_pose("hero_stand")
    assert loaded is not None
    assert loaded["pose_id"] == "hero_stand"
    assert loaded["x"] == 42

    records = registry.list_assets("poses")
    assert len(records) == 1
    assert records[0]["meta"]["pose_id"] == "hero_stand"
    assert records[0]["sidecar"].endswith(".json.asset.json")

    assert manager.remove_pose("hero_stand")
    assert not pose_file.exists()
    assert registry.list_assets("poses") == []
