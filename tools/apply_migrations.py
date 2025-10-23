from __future__ import annotations

"""
Utility script for applying ComfyVN SQL migrations.

Usage:
    python tools/apply_migrations.py --dry-run
    python tools/apply_migrations.py --db-path ./my.db --verbose
"""

import argparse
from pathlib import Path
from typing import Sequence

from comfyvn.core.db_manager import DEFAULT_DB_PATH
from comfyvn.db import MigrationRunner, load_default_migrations


def _format_versions(versions: Sequence[str]) -> str:
    return ", ".join(versions) if versions else "(none)"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply ComfyVN database migrations.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the migrations that would run without applying them.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each migration as it executes.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List applied and pending migrations without applying them.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    db_path = Path(args.db_path).expanduser()
    migrations = load_default_migrations()
    runner = MigrationRunner(db_path, migrations)

    if args.list:
        pending = runner.pending()
        applied = runner.applied_versions()
        print(f"Database: {db_path}")
        print(f"Applied: {_format_versions(applied)}")
        print(
            f"Pending: {_format_versions(tuple(migration.version for migration in pending))}"
        )
        return 0

    executed = runner.apply_all(dry_run=args.dry_run, verbose=args.verbose)
    if args.dry_run:
        print(f"Dry-run complete. Pending migrations: {_format_versions(executed)}")
        return 0

    if executed:
        print(f"Applied migrations: {_format_versions(executed)}")
    else:
        print("Database already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
