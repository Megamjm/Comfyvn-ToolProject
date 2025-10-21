"""
Timeline registry facade for the Studio shell.

Stores ordered scene sequences (timelines) for each project, including
optional metadata that can be surfaced in the GUI timeline builder.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base_registry import BaseRegistry


class TimelineRegistry(BaseRegistry):
    TABLE = "timelines"

    def list_timelines(self) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            f"SELECT id, name, scene_order, meta FROM {self.TABLE} WHERE project_id = ? ORDER BY id ASC",
            [self.project_id],
        )
        payload: List[Dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["scene_order"] = self._decode_order(record.get("scene_order"))
            record["meta"] = self._decode_meta(record.get("meta"))
            payload.append(record)
        return payload

    def get_timeline(self, timeline_id: int) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, name, scene_order, meta FROM {self.TABLE} WHERE project_id = ? AND id = ?",
            [self.project_id, timeline_id],
        )
        if not row:
            return None
        record = dict(row)
        record["scene_order"] = self._decode_order(record.get("scene_order"))
        record["meta"] = self._decode_meta(record.get("meta"))
        return record

    def save_timeline(
        self,
        *,
        name: str,
        scene_order: List[Dict[str, Any]],
        meta: Optional[Dict[str, Any]] = None,
        timeline_id: Optional[int] = None,
    ) -> int:
        order_json = json.dumps(scene_order, ensure_ascii=False)
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        if timeline_id is None:
            sql = (
                f"INSERT INTO {self.TABLE} (project_id, name, scene_order, meta) "
                "VALUES (?, ?, ?, ?)"
            )
            with self.connection() as conn:
                cur = conn.execute(sql, (self.project_id, name, order_json, meta_json))
                return int(cur.lastrowid)
        sql = (
            f"UPDATE {self.TABLE} SET name = ?, scene_order = ?, meta = ? "
            "WHERE project_id = ? AND id = ?"
        )
        with self.connection() as conn:
            conn.execute(
                sql, (name, order_json, meta_json, self.project_id, timeline_id)
            )
        return timeline_id

    def delete_timeline(self, timeline_id: int) -> None:
        sql = f"DELETE FROM {self.TABLE} WHERE project_id = ? AND id = ?"
        self.execute(sql, (self.project_id, timeline_id))

    @staticmethod
    def _decode_order(raw: Any) -> List[Dict[str, Any]]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str) and raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def _decode_meta(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                return {}
        return {}
