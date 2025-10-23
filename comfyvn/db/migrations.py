from __future__ import annotations

"""
Lightweight SQL migration runner for the ComfyVN SQLite database.

Migrations are expressed as ordered :class:`SQLMigration` entries that point to
``.sql`` files within the package.  The runner keeps track of applied
migrations in the ``schema_migrations`` table and is safe to execute multiple
times thanks to ``CREATE TABLE IF NOT EXISTS`` semantics inside each SQL file.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

SQL_DIR = Path(__file__).resolve().parent / "sql"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"


@dataclass(frozen=True)
class SQLMigration:
    """Descriptor for a single SQL migration."""

    version: str
    description: str
    sql_path: Path

    def read_sql(self) -> str:
        return self.sql_path.read_text(encoding="utf-8")


class MigrationRunner:
    """Apply SQL migrations to a SQLite database."""

    def __init__(
        self,
        db_path: Path | str,
        migrations: Sequence[SQLMigration],
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        self.migrations: tuple[SQLMigration, ...] = tuple(migrations)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @staticmethod
    def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_MIGRATIONS_TABLE} (
                version TEXT PRIMARY KEY,
                description TEXT,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    @staticmethod
    def _fetch_applied(conn: sqlite3.Connection) -> set[str]:
        cursor = conn.execute(
            f"SELECT version FROM {SCHEMA_MIGRATIONS_TABLE} ORDER BY applied_at ASC"
        )
        return {row[0] for row in cursor.fetchall()}

    @staticmethod
    def _record_migration(conn: sqlite3.Connection, migration: SQLMigration) -> None:
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {SCHEMA_MIGRATIONS_TABLE} (version, description)
            VALUES (?, ?)
            """,
            (migration.version, migration.description),
        )

    def pending(self) -> tuple[SQLMigration, ...]:
        """
        Return the tuple of migrations that still need to be applied.
        """

        with self._connect() as conn:
            self._ensure_migrations_table(conn)
            applied = self._fetch_applied(conn)
        return tuple(
            migration
            for migration in self.migrations
            if migration.version not in applied
        )

    def applied_versions(self) -> tuple[str, ...]:
        """
        Return the versions that have already been applied, in migration order.
        """

        with self._connect() as conn:
            self._ensure_migrations_table(conn)
            applied = self._fetch_applied(conn)
        return tuple(
            migration.version
            for migration in self.migrations
            if migration.version in applied
        )

    def apply_all(
        self, *, dry_run: bool = False, verbose: bool = False
    ) -> tuple[str, ...]:
        """
        Apply all pending migrations and return the versions that were run.

        When ``dry_run`` is ``True`` the migrations are not executed, but the
        versions that *would* run are still returned.
        """

        with self._connect() as conn:
            self._ensure_migrations_table(conn)
            applied = self._fetch_applied(conn)
            pending = [
                migration
                for migration in self.migrations
                if migration.version not in applied
            ]

            if dry_run:
                return tuple(migration.version for migration in pending)

            executed: list[str] = []
            for migration in pending:
                sql = migration.read_sql()
                if verbose:
                    print(f"[{migration.version}] applying {migration.sql_path.name}")
                conn.executescript(sql)
                self._record_migration(conn, migration)
                executed.append(migration.version)
            conn.commit()
        return tuple(executed)


def load_default_migrations() -> tuple[SQLMigration, ...]:
    """
    Load the built-in migrations shipped with the ComfyVN package.
    """

    baseline = SQLMigration(
        version="v0.6",
        description="Baseline schema for ComfyVN Studio",
        sql_path=SQL_DIR / "v0_6_baseline.sql",
    )
    return (baseline,)


def list_migration_versions(
    migrations: Iterable[SQLMigration],
) -> tuple[str, ...]:
    """Convenience helper returning the ordered migration versions."""

    return tuple(migration.version for migration in migrations)
