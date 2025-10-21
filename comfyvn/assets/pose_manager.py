from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from comfyvn.studio.core import AssetRegistry

LOGGER = logging.getLogger(__name__)


class PoseManager:
    """
    Registry-backed pose manager that keeps pose JSON files in sync with the
    asset database.  Pose records are stored inside the configured assets
    root (default: ``assets/poses``) and each registration writes a sidecar
    alongside the pose file.
    """

    def __init__(
        self,
        poses_dir: str | Path | None = None,
        *,
        assets_root: str | Path | None = None,
        registry: Optional[AssetRegistry] = None,
    ) -> None:
        self.registry = registry or AssetRegistry(assets_root=assets_root)
        self.assets_root = self.registry.ASSETS_ROOT.resolve()
        default_dir = self.assets_root / "poses"
        self.pose_root = (
            Path(poses_dir).expanduser().resolve() if poses_dir else default_dir
        )
        self.pose_root.mkdir(parents=True, exist_ok=True)
        if not self._is_within_assets(self.pose_root):
            LOGGER.warning(
                "Pose directory %s is outside the assets root %s; new poses will be copied into the assets registry.",
                self.pose_root,
                self.assets_root,
            )

    # ------------------------------
    # Listing helpers
    # ------------------------------
    def list(self) -> List[str]:
        """Legacy helper returning pose file paths."""
        return [str(path) for path in sorted(self.pose_root.glob("*.json"))]

    def list_poses(self) -> List[Dict[str, Any]]:
        """Return registry-backed pose metadata."""
        entries: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()

        for asset in self.registry.list_assets("poses"):
            rel_path = Path(asset["path"])
            pose_path = (self.assets_root / rel_path).resolve()
            meta = dict(asset.get("meta") or {})
            pose_id = str(meta.get("pose_id") or rel_path.stem)
            seen_ids.add(pose_id)

            preview = meta.get("preview") or {}
            thumb = asset.get("thumb")
            if thumb and not preview:
                preview = {"path": thumb, "kind": "thumbnail"}

            sidecar_path = asset.get("sidecar")
            entry = {
                "id": pose_id,
                "uid": asset.get("uid"),
                "path": str(pose_path),
                "sidecar": (
                    str((self.assets_root / sidecar_path).resolve())
                    if sidecar_path
                    else None
                ),
                "preview": preview or None,
                "meta": meta,
            }
            entries.append(entry)

        for pose_file in sorted(self.pose_root.glob("*.json")):
            pose_id = pose_file.stem
            if pose_id in seen_ids:
                continue
            entries.append(
                {
                    "id": pose_id,
                    "uid": None,
                    "path": str(pose_file),
                    "sidecar": None,
                    "preview": None,
                    "meta": {},
                }
            )

        return entries

    # ------------------------------
    # CRUD
    # ------------------------------
    def get_pose(self, pose_id: str) -> Optional[Dict[str, Any]]:
        """Load a pose dictionary by id."""
        pose_path = self._pose_file(pose_id)
        if pose_path.exists():
            return self._safe_read_pose(pose_path)

        asset = self._find_pose_asset(pose_id)
        if asset:
            pose_path = (self.assets_root / asset["path"]).resolve()
            if pose_path.exists():
                return self._safe_read_pose(pose_path)
        return None

    def add_pose(
        self,
        pose_id: str,
        data: Dict[str, Any],
        *,
        metadata: Optional[Dict[str, Any]] = None,
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        """Persist a pose JSON file and register it in the asset registry."""
        pose_id = str(pose_id).strip()
        if not pose_id:
            raise ValueError("pose_id is required")

        pose_path = self._pose_file(pose_id)
        if pose_path.exists() and not overwrite:
            raise FileExistsError(f"Pose '{pose_id}' already exists at {pose_path}")

        payload = dict(data or {})
        payload.setdefault("pose_id", pose_id)
        pose_path.parent.mkdir(parents=True, exist_ok=True)
        pose_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        meta_payload = dict(metadata or {})
        meta_payload.setdefault("pose_id", pose_id)
        meta_payload.setdefault("origin", meta_payload.get("origin") or "pose_manager")

        copy_mode = False
        dest_relative: Optional[Path]
        try:
            dest_relative = pose_path.relative_to(self.assets_root)
        except ValueError:
            dest_relative = Path("poses") / pose_path.name
            copy_mode = True

        asset_info = self.registry.register_file(
            pose_path,
            asset_type="poses",
            dest_relative=dest_relative,
            metadata=meta_payload,
            copy=copy_mode,
        )
        return asset_info

    def remove_pose(self, pose_id: str, *, delete_asset: bool = False) -> bool:
        """Remove a pose JSON file and its registry entry."""
        asset = self._find_pose_asset(pose_id)
        removed = False
        if asset and asset.get("uid"):
            removed = (
                self.registry.remove_asset(asset["uid"], delete_files=delete_asset)
                or removed
            )
        pose_path = self._pose_file(pose_id)
        if pose_path.exists():
            pose_path.unlink()
            removed = True
        return removed

    def load(self, path: str) -> Optional[Dict[str, Any]]:
        """Load a pose JSON file from an absolute path."""
        return self._safe_read_pose(Path(path))

    # ------------------------------
    # Internal helpers
    # ------------------------------
    def _pose_file(self, pose_id: str) -> Path:
        return (self.pose_root / f"{pose_id}.json").resolve()

    def _find_pose_asset(self, pose_id: str) -> Optional[Dict[str, Any]]:
        for asset in self.registry.list_assets("poses"):
            meta = asset.get("meta") or {}
            rel_path = Path(asset["path"])
            if meta.get("pose_id") == pose_id or rel_path.stem == pose_id:
                return asset
        return None

    @staticmethod
    def _safe_read_pose(path: Path) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to load pose %s: %s", path, exc)
            return None

    def _is_within_assets(self, target: Path) -> bool:
        try:
            target.resolve().relative_to(self.assets_root)
            return True
        except ValueError:
            return False
