from __future__ import annotations

"""
Seed the ComfyVN database with lightweight demo content.
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Sequence

from comfyvn.core.db_manager import DEFAULT_DB_PATH
from comfyvn.db import ensure_schema

TARGET_TABLES: tuple[str, ...] = (
    "scenes",
    "characters",
    "timelines",
    "variables",
    "templates",
    "assets_registry",
    "thumbnails",
    "provenance",
    "imports",
    "jobs",
    "providers",
    "translations",
)


def _table_has_rows(conn: sqlite3.Connection, table: str) -> bool:
    cursor = conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
    return cursor.fetchone() is not None


def _clear_tables(conn: sqlite3.Connection, tables: Iterable[str]) -> None:
    for table in tables:
        conn.execute(f"DELETE FROM {table}")


def seed_demo_data(db_path: Path | str, *, force: bool = False) -> Dict[str, int]:
    path = Path(db_path).expanduser()
    ensure_schema(path)

    inserted: Dict[str, int] = {}
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        if force:
            _clear_tables(conn, TARGET_TABLES)

        # scenes -----------------------------------------------------------------
        if force or not _table_has_rows(conn, "scenes"):
            scenes = [
                {
                    "title": "Welcome to ComfyVN",
                    "body_json": {
                        "nodes": [
                            {
                                "id": "start",
                                "type": "text",
                                "text": "Welcome to the ComfyVN demo project!",
                            },
                            {
                                "id": "choice",
                                "type": "choice",
                                "options": [
                                    {
                                        "id": "investigate",
                                        "label": "Investigate the studio",
                                    },
                                    {"id": "relax", "label": "Relax and explore"},
                                ],
                            },
                        ]
                    },
                    "meta_json": {"tags": ["demo", "intro"]},
                },
                {
                    "title": "Studio Tour",
                    "body_json": {
                        "nodes": [
                            {
                                "id": "tour",
                                "type": "text",
                                "text": "You follow the tutorial drone through the studio pipeline.",
                            }
                        ]
                    },
                    "meta_json": {"tags": ["demo"]},
                },
            ]
            conn.executemany(
                """
                INSERT INTO scenes (title, body_json, meta_json)
                VALUES (?, ?, ?)
                """,
                [
                    (
                        scene["title"],
                        json.dumps(scene["body_json"]),
                        json.dumps(scene["meta_json"]),
                    )
                    for scene in scenes
                ],
            )
            inserted["scenes"] = len(scenes)

        # characters --------------------------------------------------------------
        if force or not _table_has_rows(conn, "characters"):
            characters = [
                {
                    "name": "Nova",
                    "traits_json": {"role": "narrator", "mood": "enthusiastic"},
                    "portrait_asset_id": None,
                    "meta_json": {"color": "#7dd3fc"},
                },
                {
                    "name": "Atlas",
                    "traits_json": {"role": "guide", "mood": "calm"},
                    "portrait_asset_id": None,
                    "meta_json": {"color": "#fca5a5"},
                },
            ]
            conn.executemany(
                """
                INSERT INTO characters (name, traits_json, portrait_asset_id, meta_json)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        character["name"],
                        json.dumps(character["traits_json"]),
                        character["portrait_asset_id"],
                        json.dumps(character["meta_json"]),
                    )
                    for character in characters
                ],
            )
            inserted["characters"] = len(characters)

        # assets ------------------------------------------------------------------
        if force or not _table_has_rows(conn, "assets_registry"):
            assets = [
                {
                    "type": "image",
                    "path": "demo/cover.png",
                    "hash": "demo-hash",
                    "bytes": 1024,
                    "meta_json": {"description": "Placeholder cover art"},
                }
            ]
            conn.executemany(
                """
                INSERT INTO assets_registry (type, path, hash, bytes, meta_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        asset["type"],
                        asset["path"],
                        asset["hash"],
                        asset["bytes"],
                        json.dumps(asset["meta_json"]),
                    )
                    for asset in assets
                ],
            )
            inserted["assets_registry"] = len(assets)

        asset_id = None
        row = conn.execute(
            "SELECT id FROM assets_registry ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if row:
            asset_id = row["id"]

        if asset_id is not None and (force or not _table_has_rows(conn, "thumbnails")):
            conn.execute(
                """
                INSERT OR REPLACE INTO thumbnails (asset_id, path, w, h)
                VALUES (?, ?, ?, ?)
                """,
                (asset_id, "demo/cover_thumb.png", 400, 225),
            )
            inserted["thumbnails"] = 1

        if asset_id is not None and (force or not _table_has_rows(conn, "provenance")):
            conn.execute(
                """
                INSERT OR REPLACE INTO provenance (asset_id, seed, tool, workflow, "commit", meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    "demo-seed",
                    "demo-tool",
                    "demo-workflow",
                    "HEAD",
                    json.dumps({"notes": "Seeded by tools/seed_demo_data.py"}),
                ),
            )
            inserted["provenance"] = 1

        # timelines ----------------------------------------------------------------
        if force or not _table_has_rows(conn, "timelines"):
            scene_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM scenes ORDER BY id ASC"
                ).fetchall()
            ]
            conn.execute(
                """
                INSERT INTO timelines (name, scene_order_json, meta_json)
                VALUES (?, ?, ?)
                """,
                (
                    "Demo Timeline",
                    json.dumps({"scenes": scene_ids}),
                    json.dumps({"description": "Simple linear timeline"}),
                ),
            )
            inserted["timelines"] = 1

        # variables ----------------------------------------------------------------
        if force or not _table_has_rows(conn, "variables"):
            conn.execute(
                """
                INSERT INTO variables (scope, name, type, value_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "global",
                    "demo_mode",
                    "bool",
                    json.dumps({"value": True}),
                ),
            )
            inserted["variables"] = 1

        # templates ----------------------------------------------------------------
        if force or not _table_has_rows(conn, "templates"):
            conn.execute(
                """
                INSERT INTO templates (name, payload_json, type, meta_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "demo_notification",
                    json.dumps({"text": "Demo pipeline ready!"}),
                    "system",
                    json.dumps({"category": "notifications"}),
                ),
            )
            inserted["templates"] = 1

        # imports ------------------------------------------------------------------
        if force or not _table_has_rows(conn, "imports"):
            conn.execute(
                """
                INSERT INTO imports (kind, status, logs_path, in_json, out_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "demo",
                    "complete",
                    "logs/demo_import.log",
                    json.dumps({"source": "seed"}),
                    json.dumps({"result": "ok"}),
                ),
            )
            inserted["imports"] = 1

        # jobs ---------------------------------------------------------------------
        if force or not _table_has_rows(conn, "jobs"):
            conn.execute(
                """
                INSERT INTO jobs (kind, status, progress, meta_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "demo_render",
                    "succeeded",
                    1.0,
                    json.dumps({"notes": "Completed automatically by seeder"}),
                ),
            )
            inserted["jobs"] = 1

        # providers ----------------------------------------------------------------
        if force or not _table_has_rows(conn, "providers"):
            conn.execute(
                """
                INSERT INTO providers (name, kind, config_json, status_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "demo_provider",
                    "mock",
                    json.dumps({"base_url": "http://127.0.0.1:9999"}),
                    json.dumps({"status": "online"}),
                ),
            )
            inserted["providers"] = 1

        # translations -------------------------------------------------------------
        if force or not _table_has_rows(conn, "translations"):
            target_row = conn.execute(
                "SELECT id FROM scenes ORDER BY id ASC LIMIT 1"
            ).fetchone()
            target_id = target_row["id"] if target_row else 1
            conn.execute(
                """
                INSERT INTO translations (target_id, lang, body_json, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    target_id,
                    "es",
                    json.dumps({"text": "¡Bienvenido a ComfyVN!"}),
                    "draft",
                ),
            )
            inserted["translations"] = 1

        conn.commit()

    return inserted


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the ComfyVN database with demo data."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing demo data instead of skipping populated tables.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = seed_demo_data(args.db_path, force=args.force)
    if result:
        summary = ", ".join(
            f"{table}: {count}" for table, count in sorted(result.items())
        )
        print(f"Seeded -> {summary}")
    else:
        print("Database already contained data; nothing inserted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
