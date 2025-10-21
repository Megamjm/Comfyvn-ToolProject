"""
Canonical database schema definitions for ComfyVN v0.6.

The schema is expressed as a list of table definitions that can be applied in a
deterministic order.  Each definition provides a CREATE TABLE statement along
with optional column patch descriptors that are executed only when a column is
missing.  This allows the migration entry points to remain idempotent and safe
to run on existing SQLite files without clobbering user data.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = "v0.6"


@dataclass(frozen=True)
class ColumnPatch:
    """Represents an optional column addition to keep a table aligned."""

    name: str
    ddl: str


@dataclass(frozen=True)
class TableDefinition:
    """Wrapper describing a table and the DDL required to keep it current."""

    name: str
    create_sql: str
    column_patches: Sequence[ColumnPatch] = ()


TABLE_DEFINITIONS: tuple[TableDefinition, ...] = (
    TableDefinition(
        name="projects",
        create_sql="""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                project_id TEXT UNIQUE,
                name TEXT,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
    ),
    TableDefinition(
        name="scenes",
        create_sql="""
            CREATE TABLE IF NOT EXISTS scenes (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                title TEXT,
                body TEXT,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="characters",
        create_sql="""
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                name TEXT,
                traits JSON,
                portrait_path TEXT,
                linked_scene_ids JSON,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="timelines",
        create_sql="""
            CREATE TABLE IF NOT EXISTS timelines (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                name TEXT,
                scene_order JSON,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="variables",
        create_sql="""
            CREATE TABLE IF NOT EXISTS variables (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                scope TEXT,
                name TEXT,
                value JSON,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="templates",
        create_sql="""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                name TEXT,
                body JSON,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="worlds",
        create_sql="""
            CREATE TABLE IF NOT EXISTS worlds (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                name TEXT,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="assets_registry",
        create_sql="""
            CREATE TABLE IF NOT EXISTS assets_registry (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                uid TEXT UNIQUE,
                type TEXT,
                path_full TEXT,
                path_thumb TEXT,
                hash TEXT,
                bytes INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                meta JSON
            )
        """,
        column_patches=(
            ColumnPatch("project_id", "TEXT DEFAULT 'default'"),
            ColumnPatch("path_thumb", "TEXT"),
            ColumnPatch("hash", "TEXT"),
            ColumnPatch("bytes", "INTEGER"),
            ColumnPatch("meta", "JSON"),
        ),
    ),
    TableDefinition(
        name="provenance",
        create_sql="""
            CREATE TABLE IF NOT EXISTS provenance (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                asset_id INTEGER,
                source TEXT,
                workflow_hash TEXT,
                commit_hash TEXT,
                inputs_json JSON,
                c2pa_like JSON,
                user_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="findings",
        create_sql="""
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                issue_id TEXT UNIQUE,
                target_id TEXT,
                kind TEXT,
                message TEXT,
                severity TEXT,
                detail JSON,
                resolved INTEGER DEFAULT 0,
                notes JSON,
                timestamp REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(
            ColumnPatch("project_id", "TEXT DEFAULT 'default'"),
            ColumnPatch("notes", "JSON"),
            ColumnPatch("timestamp", "REAL"),
        ),
    ),
    TableDefinition(
        name="thumbnails",
        create_sql="""
            CREATE TABLE IF NOT EXISTS thumbnails (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                asset_id INTEGER,
                thumb_path TEXT,
                w INTEGER,
                h INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="imports",
        create_sql="""
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                path TEXT,
                kind TEXT,
                processed INTEGER DEFAULT 0,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(
            ColumnPatch("project_id", "TEXT DEFAULT 'default'"),
            ColumnPatch("processed", "INTEGER DEFAULT 0"),
        ),
    ),
    TableDefinition(
        name="providers",
        create_sql="""
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                name TEXT,
                type TEXT,
                config JSON,
                active INTEGER DEFAULT 1,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="jobs",
        create_sql="""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                type TEXT,
                status TEXT,
                submit_ts TEXT DEFAULT CURRENT_TIMESTAMP,
                done_ts TEXT,
                owner TEXT,
                input_json JSON,
                output_json JSON,
                logs_path TEXT
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="translations",
        create_sql="""
            CREATE TABLE IF NOT EXISTS translations (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                scene_id INTEGER,
                lang TEXT,
                body JSON,
                confidence REAL,
                src_lang TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
    TableDefinition(
        name="settings",
        create_sql="""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                key TEXT,
                value JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """,
        column_patches=(ColumnPatch("project_id", "TEXT DEFAULT 'default'"),),
    ),
)


def iter_tables() -> Iterator[TableDefinition]:
    """Yield table definitions in schema application order."""

    return iter(TABLE_DEFINITIONS)


def table_names() -> tuple[str, ...]:
    """Return the ordered tuple of table names for the schema."""

    return tuple(table.name for table in TABLE_DEFINITIONS)


def ensure_schema(db_path: Path | str) -> None:
    """
    Ensure the schema exists for the provided SQLite database path.

    The function is safe to call multiple times and creates missing parent
    directories for the database file before opening the connection.
    """

    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        apply_schema(conn)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply v0.6 table definitions and column patches to an open connection."""

    conn.execute("PRAGMA foreign_keys=ON;")
    for table in TABLE_DEFINITIONS:
        LOGGER.debug("Ensuring table %s", table.name)
        conn.execute(table.create_sql)
        if table.column_patches:
            _apply_column_patches(conn, table.name, table.column_patches)
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


def _apply_column_patches(
    conn: sqlite3.Connection, table_name: str, patches: Iterable[ColumnPatch]
) -> None:
    """Add missing columns to an existing table without clobbering data."""

    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    existing = {row[1] for row in cursor.fetchall()}
    for patch in patches:
        if patch.name in existing:
            continue
        LOGGER.debug("Applying column patch %s.%s", table_name, patch.name)
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {patch.name} {patch.ddl}")
