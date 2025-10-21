"""
Database manager utilities for the ComfyVN Studio SQLite backend.

The goal of this module is to centralise schema management for the v0.6
Studio data layer.  It exposes a small helper that applies the canonical
tables and ensures the migration scripts can be run idempotently both
from code and from the rebuild CLI entry point.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

LOGGER = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("comfyvn/data/comfyvn.db")


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


class DBManager:
    """Lightweight helper that applies the v0.6 schema and optional patches."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def ensure_schema(self) -> None:
        """Apply all table definitions and column patches idempotently."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            for table in TABLE_DEFINITIONS:
                LOGGER.debug("Ensuring table %s", table.name)
                conn.execute(table.create_sql)
                if table.column_patches:
                    self._apply_column_patches(conn, table.name, table.column_patches)
            conn.commit()

    def existing_tables(self) -> set[str]:
        """Return the set of tables currently present in the database."""
        query = "SELECT name FROM sqlite_master WHERE type='table'"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query).fetchall()
        return {row[0] for row in rows}

    def _apply_column_patches(
        self, conn: sqlite3.Connection, table_name: str, patches: Iterable[ColumnPatch]
    ) -> None:
        """Add missing columns to an existing table without clobbering data."""
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        existing = {row[1] for row in cursor.fetchall()}
        for patch in patches:
            if patch.name in existing:
                continue
            LOGGER.debug("Applying column patch %s.%s", table_name, patch.name)
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {patch.name} {patch.ddl}")
