"""
World registry facade for the Studio shell.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_registry import BaseRegistry


class WorldRegistry(BaseRegistry):
    TABLE = "worlds"

    def list_worlds(self) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            f"SELECT id, name, meta FROM {self.TABLE} WHERE project_id = ? ORDER BY name ASC",
            [self.project_id],
        )
        return [dict(row) for row in rows]

    def get_world(self, world_id: int) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, name, meta FROM {self.TABLE} WHERE project_id = ? AND id = ?",
            [self.project_id, world_id],
        )
        return dict(row) if row else None
