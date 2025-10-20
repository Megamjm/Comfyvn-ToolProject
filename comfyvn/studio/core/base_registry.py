"""
Shared SQLite access helpers for the Studio registries.

The goal is to provide a single, centralised location where all studio
components obtain their database connections.  Higher-level registries
subclass :class:`BaseRegistry` and implement domain-specific helpers.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Iterable, Optional

DEFAULT_DB_PATH = Path("comfyvn/data/comfyvn.db")


class BaseRegistry:
    """Base class for registry objects backed by SQLite."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH, project_id: str = "default"):
        self.db_path = Path(db_path)
        self.project_id = project_id
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Hook for subclasses that need to create tables."""
        # Base implementation creates the database file if it does not exist.
        if not self.db_path.exists():
            # touching the file is enough; schema will be applied by migration scripts.
            self.db_path.touch()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a SQLite connection with row factory set to dict-like rows."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def execute(self, sql: str, params: Iterable | None = None) -> None:
        """Execute a SQL statement that does not return rows."""
        with self.connection() as conn:
            conn.execute(sql, params or [])

    def fetchall(self, sql: str, params: Iterable | None = None) -> list[sqlite3.Row]:
        with self.connection() as conn:
            cur = conn.execute(sql, params or [])
            return cur.fetchall()

    def fetchone(self, sql: str, params: Iterable | None = None) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            cur = conn.execute(sql, params or [])
            return cur.fetchone()

    @staticmethod
    def dumps(obj: object) -> str:
        return json.dumps(obj, ensure_ascii=False)
