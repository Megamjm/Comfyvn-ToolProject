"""
Database utilities and schema helpers for ComfyVN.

This package currently exposes the canonical v0.6 schema alongside helper
functions that make it easy to ensure a SQLite database is in sync with the
expected tables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence, Set

from .migrations import (
    MigrationRunner,
    SQLMigration,
    list_migration_versions,
    load_default_migrations,
)
from .schema_v06 import (  # re-exported for convenience
    SCHEMA_VERSION,
    TABLE_DEFINITIONS,
    ColumnPatch,
    TableDefinition,
    ensure_schema,
    existing_tables,
    iter_tables,
    table_names,
)

__all__ = [
    "SCHEMA_VERSION",
    "ColumnPatch",
    "TableDefinition",
    "ensure_schema",
    "existing_tables",
    "iter_tables",
    "table_names",
    "TABLE_DEFINITIONS",
    "MigrationRunner",
    "SQLMigration",
    "load_default_migrations",
    "list_migration_versions",
]


def ensure_all(db_path: Path | str) -> None:
    """
    Public helper that mirrors :func:`ensure_schema`.

    Included for callers that expect a more generic name.
    """

    ensure_schema(db_path)


def describe_tables() -> Sequence[str]:
    """
    Return an ordered sequence of table names present in the v0.6 schema.
    """

    return [table.name for table in iter_tables()]


def ensure_many(paths: Iterable[Path | str]) -> Set[Path]:
    """
    Ensure the schema for a collection of database paths and return the
    resolved paths that were processed.
    """

    processed: set[Path] = set()
    for candidate in paths:
        path = Path(candidate).expanduser().resolve()
        ensure_schema(path)
        processed.add(path)
    return processed
