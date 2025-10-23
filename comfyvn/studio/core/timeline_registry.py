"""
Timeline registry facade for the Studio shell.

Stores ordered scene sequences (timelines) for each project, including
optional metadata that can be surfaced in the GUI timeline builder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_registry import BaseRegistry


class TimelineRegistry(BaseRegistry):
    TABLE = "timelines"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._bootstrap_checked = False

    def list_timelines(self) -> List[Dict[str, Any]]:
        self._ensure_seeded()
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
        self._ensure_seeded()
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

    def _ensure_seeded(self) -> None:
        if getattr(self, "_bootstrap_checked", False):
            return
        self._bootstrap_checked = True
        existing = self.fetchone(
            f"SELECT 1 FROM {self.TABLE} WHERE project_id = ? LIMIT 1",
            [self.project_id],
        )
        if existing:
            return
        self._seed_from_world_examples()

    def _seed_from_world_examples(self) -> None:
        root = Path("data/worlds")
        if not root.exists():
            return
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            world_id = folder.name
            examples_dir = folder / "examples"
            scene_files = sorted(examples_dir.glob("*.scene.json"))
            scene_order: List[Dict[str, Any]] = []
            for scene_path in scene_files:
                try:
                    data = json.loads(scene_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                scene_order.append(
                    {
                        "scene_id": data.get("id"),
                        "title": data.get("title"),
                        "world_id": world_id,
                        "summary": data.get("summary"),
                        "location": data.get("location"),
                        "tags": data.get("tags") or [],
                    }
                )
            if not scene_order:
                continue
            meta: Dict[str, Any] = {
                "world_id": world_id,
                "source": "world_seed_v1",
            }
            epochs_file = folder / "timeline" / "epochs.json"
            if epochs_file.exists():
                try:
                    epochs_payload = json.loads(epochs_file.read_text(encoding="utf-8"))
                    if isinstance(epochs_payload, dict):
                        meta["epochs"] = epochs_payload.get("epochs")
                except Exception:
                    pass
            name = f"{world_id.replace('_', ' ').title()} Openers"
            self.save_timeline(name=name, scene_order=scene_order, meta=meta)

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
