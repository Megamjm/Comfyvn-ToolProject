"""
Canonical database schema metadata for ComfyVN v0.6.

The runtime schema is applied via SQL migrations (see :mod:`comfyvn.db.migrations`).
The objects declared in this module provide metadata about the schema for callers
that need to inspect table layouts or ensure the migrations are executed.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from comfyvn.db.migrations import MigrationRunner, SQLMigration, load_default_migrations

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = "v0.6"


@dataclass(frozen=True)
class ColumnPatch:
    """
    Backwards-compatible placeholder for historic schema patch descriptors.

    The SQL migration flow renders these unnecessary, but a handful of callers
    still import the symbol from :mod:`comfyvn.db`.  Keeping the dataclass avoids
    breaking those imports while signalling that column patches are no longer
    part of the v0.6 flow.
    """

    name: str
    ddl: str


@dataclass(frozen=True)
class ColumnDefinition:
    """Describes a single column in the v0.6 schema."""

    name: str
    type: str
    description: str | None = None


@dataclass(frozen=True)
class TableDefinition:
    """Human-friendly representation of a table used for documentation purposes."""

    name: str
    columns: Sequence[ColumnDefinition]
    description: str | None = None


TABLE_DEFINITIONS: tuple[TableDefinition, ...] = (
    TableDefinition(
        name="scenes",
        description="Scripted scenes containing narrative nodes.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("title", "TEXT NOT NULL"),
            ColumnDefinition("body_json", "TEXT"),
            ColumnDefinition("meta_json", "TEXT"),
            ColumnDefinition(
                "created_at",
                "TEXT DEFAULT CURRENT_TIMESTAMP",
                "ISO-8601 timestamp for creation.",
            ),
        ),
    ),
    TableDefinition(
        name="characters",
        description="Character roster and associated metadata.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("name", "TEXT NOT NULL"),
            ColumnDefinition("traits_json", "TEXT"),
            ColumnDefinition(
                "portrait_asset_id",
                "INTEGER",
                "Foreign key -> assets_registry.id",
            ),
            ColumnDefinition("meta_json", "TEXT"),
        ),
    ),
    TableDefinition(
        name="timelines",
        description="Ordered collections of scene identifiers.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("name", "TEXT NOT NULL"),
            ColumnDefinition("scene_order_json", "TEXT"),
            ColumnDefinition("meta_json", "TEXT"),
        ),
    ),
    TableDefinition(
        name="variables",
        description="Runtime or authoring variables scoped by namespace.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("scope", "TEXT NOT NULL"),
            ColumnDefinition("name", "TEXT NOT NULL"),
            ColumnDefinition("type", "TEXT NOT NULL"),
            ColumnDefinition("value_json", "TEXT"),
        ),
    ),
    TableDefinition(
        name="templates",
        description="Reusable payload templates for orchestrations.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("name", "TEXT NOT NULL"),
            ColumnDefinition("payload_json", "TEXT"),
            ColumnDefinition("type", "TEXT"),
            ColumnDefinition("meta_json", "TEXT"),
        ),
    ),
    TableDefinition(
        name="assets_registry",
        description="Registry of all binary or external assets.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("type", "TEXT NOT NULL"),
            ColumnDefinition("path", "TEXT NOT NULL"),
            ColumnDefinition("hash", "TEXT"),
            ColumnDefinition("bytes", "INTEGER"),
            ColumnDefinition("meta_json", "TEXT"),
            ColumnDefinition(
                "created_at",
                "TEXT DEFAULT CURRENT_TIMESTAMP",
                "ISO-8601 timestamp for registration.",
            ),
        ),
    ),
    TableDefinition(
        name="thumbnails",
        description="Derived thumbnails for assets (1:1 mapping).",
        columns=(
            ColumnDefinition("asset_id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("path", "TEXT NOT NULL"),
            ColumnDefinition("w", "INTEGER NOT NULL"),
            ColumnDefinition("h", "INTEGER NOT NULL"),
        ),
    ),
    TableDefinition(
        name="provenance",
        description="Provenance metadata associated with assets.",
        columns=(
            ColumnDefinition("asset_id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("seed", "TEXT"),
            ColumnDefinition("tool", "TEXT"),
            ColumnDefinition("workflow", "TEXT"),
            ColumnDefinition("commit", "TEXT"),
            ColumnDefinition("meta_json", "TEXT"),
        ),
    ),
    TableDefinition(
        name="imports",
        description="Historical import runs and their payloads.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("kind", "TEXT NOT NULL"),
            ColumnDefinition("status", "TEXT NOT NULL"),
            ColumnDefinition("logs_path", "TEXT"),
            ColumnDefinition("in_json", "TEXT"),
            ColumnDefinition("out_json", "TEXT"),
            ColumnDefinition(
                "created_at",
                "TEXT DEFAULT CURRENT_TIMESTAMP",
                "ISO-8601 timestamp for the import record.",
            ),
        ),
    ),
    TableDefinition(
        name="jobs",
        description="Background job queue with progress tracking.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("kind", "TEXT NOT NULL"),
            ColumnDefinition("status", "TEXT NOT NULL"),
            ColumnDefinition("progress", "REAL DEFAULT 0"),
            ColumnDefinition("meta_json", "TEXT"),
            ColumnDefinition(
                "created_at",
                "TEXT DEFAULT CURRENT_TIMESTAMP",
                "ISO-8601 timestamp for job submission.",
            ),
            ColumnDefinition(
                "updated_at",
                "TEXT DEFAULT CURRENT_TIMESTAMP",
                "ISO-8601 timestamp for latest progress update.",
            ),
        ),
    ),
    TableDefinition(
        name="providers",
        description="Provider configurations and status payloads.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("name", "TEXT NOT NULL"),
            ColumnDefinition("kind", "TEXT NOT NULL"),
            ColumnDefinition("config_json", "TEXT"),
            ColumnDefinition("status_json", "TEXT"),
        ),
    ),
    TableDefinition(
        name="translations",
        description="Localised variants of narrative content.",
        columns=(
            ColumnDefinition("id", "INTEGER PRIMARY KEY"),
            ColumnDefinition("target_id", "INTEGER NOT NULL"),
            ColumnDefinition("lang", "TEXT NOT NULL"),
            ColumnDefinition("body_json", "TEXT"),
            ColumnDefinition("status", "TEXT NOT NULL"),
        ),
    ),
    TableDefinition(
        name="settings",
        description="Key/value JSON settings store.",
        columns=(
            ColumnDefinition("key", "TEXT PRIMARY KEY"),
            ColumnDefinition("value_json", "TEXT"),
        ),
    ),
)

MIGRATIONS: tuple[SQLMigration, ...] = load_default_migrations()


def iter_tables() -> Iterator[TableDefinition]:
    """Yield table definitions in schema order."""

    return iter(TABLE_DEFINITIONS)


def table_names() -> tuple[str, ...]:
    """Return the ordered tuple of table names for the schema."""

    return tuple(table.name for table in TABLE_DEFINITIONS)


def ensure_schema(db_path: Path | str) -> None:
    """
    Ensure the schema exists for the provided SQLite database path.
    """

    runner = MigrationRunner(db_path, MIGRATIONS)
    runner.apply_all()


def apply_schema(conn: sqlite3.Connection) -> None:
    """
    Apply the schema to an existing SQLite connection.

    This helper mirrors the ``ensure_schema`` semantics and is primarily kept
    for backwards compatibility with callers that inject their own connection
    objects (for example during tests).
    """

    if conn is None:
        raise ValueError("A valid sqlite3.Connection is required.")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            description TEXT,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    applied = {
        row[0]
        for row in conn.execute(
            "SELECT version FROM schema_migrations ORDER BY applied_at ASC"
        ).fetchall()
    }
    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        LOGGER.debug("Applying migration %s", migration.version)
        conn.executescript(migration.read_sql())
        conn.execute(
            """
            INSERT OR REPLACE INTO schema_migrations (version, description)
            VALUES (?, ?)
            """,
            (migration.version, migration.description),
        )
    conn.commit()


def existing_tables(db_path: Path | str) -> set[str]:
    """
    Return the set of tables currently present in the database at ``db_path``.
    """

    path = Path(db_path).expanduser()
    with sqlite3.connect(path) as conn:
        query = "SELECT name FROM sqlite_master WHERE type='table'"
        rows = conn.execute(query).fetchall()
    return {row[0] for row in rows}
