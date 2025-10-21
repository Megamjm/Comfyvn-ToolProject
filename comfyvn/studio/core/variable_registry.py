"""
Variable registry for the Studio shell.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_registry import BaseRegistry


class VariableRegistry(BaseRegistry):
    TABLE = "variables"

    def list_variables(self, scope: Optional[str] = None) -> List[Dict[str, Any]]:
        if scope:
            rows = self.fetchall(
                f"SELECT id, scope, name, value, meta FROM {self.TABLE} WHERE project_id = ? AND scope = ? ORDER BY name ASC",
                [self.project_id, scope],
            )
        else:
            rows = self.fetchall(
                f"SELECT id, scope, name, value, meta FROM {self.TABLE} WHERE project_id = ? ORDER BY scope, name ASC",
                [self.project_id],
            )
        return [dict(row) for row in rows]

    def get_variable(self, variable_id: int) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, scope, name, value, meta FROM {self.TABLE} WHERE project_id = ? AND id = ?",
            [self.project_id, variable_id],
        )
        return dict(row) if row else None
