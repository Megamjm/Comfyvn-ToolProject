"""
Provenance registry helpers for assets.

Each record links an asset to its source workflow metadata so downstream export
pipelines can reconstruct how the asset was produced.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from .base_registry import BaseRegistry

LOGGER = logging.getLogger(__name__)


class ProvenanceRegistry(BaseRegistry):
    TABLE = "provenance"

    def record(
        self,
        asset_id: int,
        *,
        source: str,
        workflow_hash: Optional[str] = None,
        commit_hash: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        c2pa_like: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a provenance row for the given asset and return the stored payload."""
        inputs_json = self.dumps(inputs or {})
        workflow = workflow_hash or self._hash_inputs(source, inputs)

        with self.connection() as conn:
            cur = conn.execute(
                f"""
                INSERT INTO {self.TABLE} (project_id, asset_id, source, workflow_hash, commit_hash, inputs_json, c2pa_like, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.project_id,
                    asset_id,
                    source,
                    workflow,
                    commit_hash,
                    inputs_json,
                    self.dumps(c2pa_like or {}),
                    user_id,
                ),
            )
            provenance_id = int(cur.lastrowid)

            row = conn.execute(
                f"""
                SELECT id, asset_id, source, workflow_hash, commit_hash, inputs_json, c2pa_like, user_id, created_at
                FROM {self.TABLE}
                WHERE project_id = ? AND id = ?
                """,
                (self.project_id, provenance_id),
            ).fetchone()

        record = dict(row)
        record["inputs"] = json.loads(record.pop("inputs_json") or "{}")
        record["c2pa_like"] = json.loads(record.pop("c2pa_like") or "{}")

        LOGGER.debug("Recorded provenance id=%s asset_id=%s source=%s", provenance_id, asset_id, source)
        return record

    def list_for_asset_uid(self, asset_uid: str) -> List[Dict[str, Any]]:
        """Return provenance records for a given asset UID."""
        rows = self.fetchall(
            """
            SELECT p.id, p.asset_id, p.source, p.workflow_hash, p.commit_hash,
                   p.inputs_json, p.c2pa_like, p.user_id, p.created_at
            FROM provenance AS p
            JOIN assets_registry AS a ON a.id = p.asset_id
            WHERE p.project_id = ? AND a.project_id = ? AND a.uid = ?
            ORDER BY p.id DESC
            """,
            (self.project_id, self.project_id, asset_uid),
        )
        results: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["inputs"] = json.loads(payload.pop("inputs_json") or "{}")
            payload["c2pa_like"] = json.loads(payload.pop("c2pa_like") or "{}")
            results.append(payload)
        return results

    @staticmethod
    def _hash_inputs(source: str, inputs: Optional[Dict[str, Any]]) -> Optional[str]:
        """Derive a deterministic workflow hash from the supplied inputs."""
        if not inputs:
            return None
        digest = hashlib.sha256()
        digest.update(source.strip().encode("utf-8"))
        digest.update(json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        return digest.hexdigest()
