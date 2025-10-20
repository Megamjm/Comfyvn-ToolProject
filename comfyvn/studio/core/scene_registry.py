"""
Scene registry facade for the Studio shell.

This module exposes a simple CRUD interface over the `scenes` table.
It currently provides minimal functionality so the Studio shell can
query the available scenes while the full v0.6 schema is being built.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_registry import BaseRegistry


class SceneRegistry(BaseRegistry):
    TABLE = "scenes"

    def list_scenes(self) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            f"SELECT id, title, meta FROM {self.TABLE} WHERE project_id = ? ORDER BY id ASC",
            [self.project_id],
        )
        return [dict(row) for row in rows]

    def get_scene(self, scene_id: int) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, title, body, meta FROM {self.TABLE} WHERE project_id = ? AND id = ?",
            [self.project_id, scene_id],
        )
        return dict(row) if row else None

    def upsert_scene(self, title: str, body: str, meta: Dict[str, Any], scene_id: Optional[int] = None) -> int:
        """Insert or update a scene; returns the database ID."""
        meta_json = self.dumps(meta or {})
        payload = (self.project_id, title, body, meta_json)
        if scene_id is None:
            sql = f"INSERT INTO {self.TABLE} (project_id, title, body, meta) VALUES (?, ?, ?, ?)"
            with self.connection() as conn:
                cur = conn.execute(sql, payload)
                return cur.lastrowid
        sql = f"UPDATE {self.TABLE} SET title = ?, body = ?, meta = ? WHERE project_id = ? AND id = ?"
        with self.connection() as conn:
            conn.execute(sql, (title, body, meta_json, self.project_id, scene_id))
            return scene_id
