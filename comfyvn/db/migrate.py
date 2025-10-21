"""
Command-line helper for applying ComfyVN database migrations.

Usage examples:

    python -m comfyvn.db.migrate up --target v0.6

The CLI is intentionally simple: only ``up`` migrations are supported and each
target corresponds to a one-shot schema application that can be executed
multiple times safely.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, Tuple

from comfyvn.core.db_manager import DEFAULT_DB_PATH
from comfyvn.db import schema_v06

LOGGER = logging.getLogger(__name__)

MigrationFunc = Callable[[Path | str], None]
ExistingTablesFunc = Callable[[Path | str], Iterable[str]]


class MigrationTarget:
    """Descriptor for a supported migration target."""

    def __init__(
        self,
        version: str,
        apply: MigrationFunc,
        tables: ExistingTablesFunc,
        description: str,
    ) -> None:
        self.version = version
        self.apply = apply
        self.tables = tables
        self.description = description

    def ensure(self, db_path: Path | str) -> Tuple[str, Iterable[str]]:
        """Apply the migration and return the discovered tables."""

        LOGGER.debug("Applying migration target %s to %s", self.version, db_path)
        self.apply(db_path)
        return self.version, self.tables(db_path)


TARGETS: Dict[str, MigrationTarget] = {
    schema_v06.SCHEMA_VERSION: MigrationTarget(
        version=schema_v06.SCHEMA_VERSION,
        apply=schema_v06.ensure_schema,
        tables=schema_v06.existing_tables,
        description="Canonical Studio schema (scenes, assets, jobs, imports, ...).",
    ),
}


def migrate_up(target: str, db_path: Path | str, quiet: bool = False) -> Iterable[str]:
    """
    Apply the requested migration target to ``db_path``.

    Returns the collection of tables present after the migration runs.
    """

    if target not in TARGETS:
        known = ", ".join(sorted(TARGETS))
        raise ValueError(f"Unknown migration target '{target}'. Known targets: {known}")

    resolved = Path(db_path).expanduser()
    version, tables = TARGETS[target].ensure(resolved)

    if not quiet:
        table_list = ", ".join(sorted(tables))
        print(f"[{version}] ✅ ensured schema at {resolved}")
        print(f"[{version}] tables: {table_list}")

    return tables


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the migration CLI."""

    parser = argparse.ArgumentParser(
        prog="comfyvn.db.migrate",
        description="Apply ComfyVN database migrations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    up_parser = subparsers.add_parser(
        "up",
        help="Apply (or reapply) a schema target to the database.",
    )
    up_parser.add_argument(
        "--target",
        default=schema_v06.SCHEMA_VERSION,
        choices=sorted(TARGETS),
        help="Schema target to apply (default: v0.6).",
    )
    up_parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH}).",
    )
    up_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-friendly output; useful for scripting.",
    )
    up_parser.add_argument(
        "--list-targets",
        action="store_true",
        help="List available targets and exit without applying migrations.",
    )

    return parser


def list_targets() -> None:
    """Print the available migration targets."""

    print("Available migration targets:")
    for key, descriptor in sorted(TARGETS.items()):
        print(f"  - {key}: {descriptor.description}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.command == "up":
        if args.list_targets:
            list_targets()
            return 0
        try:
            migrate_up(args.target, args.db_path, quiet=args.quiet)
        except ValueError as exc:
            LOGGER.error("%s", exc)
            return 1
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
