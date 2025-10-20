"""
Character registry facade for the Studio shell.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_registry import BaseRegistry


class CharacterRegistry(BaseRegistry):
    TABLE = "characters"

    def list_characters(self) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            f"SELECT id, name, meta FROM {self.TABLE} WHERE project_id = ? ORDER BY name ASC",
            [self.project_id],
        )
        return [dict(row) for row in rows]

    def get_character(self, character_id: int) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, name, traits, meta FROM {self.TABLE} WHERE project_id = ? AND id = ?",
            [self.project_id, character_id],
        )
        return dict(row) if row else None

    def upsert_character(
        self,
        name: str,
        *,
        traits: Optional[Dict[str, Any]] = None,
        portrait_path: Optional[str] = None,
        linked_scene_ids: Optional[List[int]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Insert or update a character by name; returns database ID."""
        traits_json = self.dumps(traits or {})
        meta_json = self.dumps(meta or {})
        linked_json = self.dumps(linked_scene_ids or [])

        with self.connection() as conn:
            cur = conn.execute(
                f"SELECT id, linked_scene_ids FROM {self.TABLE} WHERE project_id = ? AND name = ?",
                (self.project_id, name),
            )
            row = cur.fetchone()
            if row:
                if linked_scene_ids is None:
                    # Preserve any existing links if caller did not provide them.
                    linked_json = row["linked_scene_ids"] or self.dumps([])
                conn.execute(
                    f"""
                    UPDATE {self.TABLE}
                    SET traits = ?, portrait_path = ?, linked_scene_ids = ?, meta = ?
                    WHERE project_id = ? AND id = ?
                    """,
                    (traits_json, portrait_path, linked_json, meta_json, self.project_id, row["id"]),
                )
                return int(row["id"])

            new_cur = conn.execute(
                f"""
                INSERT INTO {self.TABLE} (project_id, name, traits, portrait_path, linked_scene_ids, meta)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (self.project_id, name, traits_json, portrait_path, linked_json, meta_json),
            )
            return int(new_cur.lastrowid)

    def append_scene_link(self, character_id: int, scene_id: int) -> None:
        """Attach a scene reference to the character's linked_scene_ids list."""
        with self.connection() as conn:
            cur = conn.execute(
                f"SELECT linked_scene_ids FROM {self.TABLE} WHERE project_id = ? AND id = ?",
                (self.project_id, character_id),
            )
            row = cur.fetchone()

            links: List[int] = []
            if row and row["linked_scene_ids"]:
                try:
                    import json

                    links = json.loads(row["linked_scene_ids"])
                except Exception:
                    links = []

            if scene_id not in links:
                links.append(scene_id)
                conn.execute(
                    f"UPDATE {self.TABLE} SET linked_scene_ids = ? WHERE project_id = ? AND id = ?",
                    (self.dumps(links), self.project_id, character_id),
                )
