"""
Database manager utilities for the ComfyVN Studio SQLite backend.

The goal of this module is to centralise schema management for the v0.6
Studio data layer.  It exposes a small helper that applies the canonical
tables and ensures the migration scripts can be run idempotently both
from code and from the rebuild CLI entry point.
"""

from __future__ import annotations

import logging
from pathlib import Path

from comfyvn.db import schema_v06

LOGGER = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("comfyvn/data/comfyvn.db")

# Re-export schema primitives for callers that imported them from this module.
ColumnPatch = schema_v06.ColumnPatch
TableDefinition = schema_v06.TableDefinition
TABLE_DEFINITIONS = schema_v06.TABLE_DEFINITIONS


class DBManager:
    """Lightweight helper that applies the v0.6 schema and optional patches."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def ensure_schema(self) -> None:
        """Apply all table definitions and column patches idempotently."""

        LOGGER.debug("Ensuring schema for %s", self.db_path)
        schema_v06.ensure_schema(self.db_path)

    def existing_tables(self) -> set[str]:
        """Return the set of tables currently present in the database."""

        return schema_v06.existing_tables(self.db_path)
