"""
Import registry helpers for recording inbound content pipelines.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .base_registry import BaseRegistry

LOGGER = logging.getLogger(__name__)


class ImportRegistry(BaseRegistry):
    TABLE = "imports"

    def record_import(
        self,
        *,
        path: str,
        kind: str,
        processed: bool = False,
        meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        meta_json = self.dumps(meta or {})
        with self.connection() as conn:
            cur = conn.execute(
                f"""
                INSERT INTO {self.TABLE} (project_id, path, kind, processed, meta)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.project_id, path, kind, int(processed), meta_json),
            )
            import_id = cur.lastrowid
        LOGGER.debug("Recorded import %s (%s)", import_id, kind)
        return int(import_id)

    def mark_processed(
        self, import_id: int, *, meta: Optional[Dict[str, Any]] = None
    ) -> None:
        fields = ["processed = 1"]
        params: list[Any] = []
        if meta is not None:
            fields.append("meta = ?")
            params.append(self.dumps(meta))
        params.extend([self.project_id, import_id])
        sql = f"UPDATE {self.TABLE} SET {', '.join(fields)} WHERE project_id = ? AND id = ?"
        with self.connection() as conn:
            conn.execute(sql, params)
        LOGGER.debug("Marked import %s processed", import_id)

    def update_meta(self, import_id: int, meta: Dict[str, Any]) -> None:
        with self.connection() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET meta = ? WHERE project_id = ? AND id = ?",
                (self.dumps(meta), self.project_id, import_id),
            )
        LOGGER.debug("Updated import %s metadata", import_id)

    def get_import(self, import_id: int) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, path, kind, processed, meta, created_at "
            f"FROM {self.TABLE} WHERE project_id = ? AND id = ?",
            [self.project_id, import_id],
        )
        return dict(row) if row else None
