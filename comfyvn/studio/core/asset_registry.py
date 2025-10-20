"""
Asset registry facade for the Studio shell.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_registry import BaseRegistry


class AssetRegistry(BaseRegistry):
    TABLE = "assets_registry"

    def list_assets(self, asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if asset_type:
            rows = self.fetchall(
                f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
                f"FROM {self.TABLE} WHERE project_id = ? AND type = ? ORDER BY id DESC",
                [self.project_id, asset_type],
            )
        else:
            rows = self.fetchall(
                f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
                f"FROM {self.TABLE} WHERE project_id = ? ORDER BY id DESC",
                [self.project_id],
            )
        return [dict(row) for row in rows]

    def get_asset(self, uid: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
            f"FROM {self.TABLE} WHERE project_id = ? AND uid = ?",
            [self.project_id, uid],
        )
        return dict(row) if row else None
