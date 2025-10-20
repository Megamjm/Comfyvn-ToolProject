"""
Job registry facade for tracking background jobs initiated by the Studio shell.

The table schema is provisioned via ``tools/apply_phase06_rebuild.py`` and
contains generic fields that we reuse for import pipelines.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base_registry import BaseRegistry

LOGGER = logging.getLogger(__name__)


class JobRegistry(BaseRegistry):
    TABLE = "jobs"

    def create_job(
        self,
        job_type: str,
        *,
        owner: str = "system",
        status: str = "running",
        input_payload: Optional[Dict[str, Any]] = None,
        logs_path: Optional[str] = None,
    ) -> int:
        """Insert a new job row and return its database identifier."""
        payload_json = self.dumps(input_payload or {})
        with self.connection() as conn:
            cur = conn.execute(
                f"""
                INSERT INTO {self.TABLE} (project_id, type, status, owner, input_json, logs_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (self.project_id, job_type, status, owner, payload_json, logs_path),
            )
            job_id = cur.lastrowid
        LOGGER.debug("Created job %s (%s)", job_id, job_type)
        return int(job_id)

    def update_job(
        self,
        job_id: int,
        *,
        status: Optional[str] = None,
        output_payload: Optional[Dict[str, Any]] = None,
        logs_path: Optional[str] = None,
    ) -> None:
        """Update the specified job with status/output/log paths."""
        fields = []
        params: List[Any] = []

        if status is not None:
            fields.append("status = ?")
            params.append(status)
            if status in {"completed", "failed"}:
                fields.append("done_ts = CURRENT_TIMESTAMP")

        if output_payload is not None:
            fields.append("output_json = ?")
            params.append(self.dumps(output_payload))

        if logs_path is not None:
            fields.append("logs_path = ?")
            params.append(logs_path)

        if not fields:
            LOGGER.debug("No updates applied to job %s", job_id)
            return

        params.extend([self.project_id, job_id])
        sql = f"UPDATE {self.TABLE} SET {', '.join(fields)} WHERE project_id = ? AND id = ?"
        with self.connection() as conn:
            conn.execute(sql, params)
        LOGGER.debug("Updated job %s", job_id)

    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, type, status, submit_ts, done_ts, owner, input_json, output_json, logs_path "
            f"FROM {self.TABLE} WHERE project_id = ? AND id = ?",
            [self.project_id, job_id],
        )
        return dict(row) if row else None

    def list_jobs(self, job_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        params: List[Any] = [self.project_id]
        where = ""
        if job_type:
            where = "AND type = ?"
            params.append(job_type)
        params.append(limit)
        rows = self.fetchall(
            f"""
            SELECT id, type, status, submit_ts, done_ts, owner, logs_path
            FROM {self.TABLE}
            WHERE project_id = ? {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        )
        return [dict(row) for row in rows]
