"""
Phase 0 (v0.6) rebuild helper.

This script recreates the canonical directory layout and bootstraps the
SQLite database tables required by the upcoming Studio shell.  It is safe
to run multiple times; existing tables are created if missing.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
DB_PATH = ROOT / "comfyvn" / "data" / "comfyvn.db"

DIRS = [
    ROOT / "logs",
    ROOT / "exports",
    ROOT / "cache" / "sprites",
    ROOT / "cache" / "thumbs",
    ROOT / "comfyvn" / "data" / "templates",
    ROOT / "comfyvn" / "data" / "settings",
    ROOT / "comfyvn" / "data" / "variables",
    DATA_ROOT / "assets" / "_meta",
    DATA_ROOT / "assets" / "characters",
    DATA_ROOT / "assets" / "backgrounds",
    DATA_ROOT / "assets" / "music",
    DATA_ROOT / "assets" / "voices",
]


SCHEMA = [
    "PRAGMA foreign_keys=ON;",
    "CREATE TABLE IF NOT EXISTS projects ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT UNIQUE,"
    "    name TEXT,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS scenes ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    title TEXT,"
    "    body TEXT,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS characters ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    name TEXT,"
    "    traits JSON,"
    "    portrait_path TEXT,"
    "    linked_scene_ids JSON,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS timelines ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    name TEXT,"
    "    scene_order JSON,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS variables ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    scope TEXT,"
    "    name TEXT,"
    "    value JSON,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS templates ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    name TEXT,"
    "    body JSON,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS worlds ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    name TEXT,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS assets_registry ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    uid TEXT UNIQUE,"
    "    type TEXT,"
    "    path_full TEXT,"
    "    path_thumb TEXT,"
    "    hash TEXT,"
    "    bytes INTEGER,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
    "    meta JSON"
    ");",
    "CREATE TABLE IF NOT EXISTS provenance ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    asset_id INTEGER,"
    "    source TEXT,"
    "    workflow_hash TEXT,"
    "    commit_hash TEXT,"
    "    inputs_json JSON,"
    "    c2pa_like JSON,"
    "    user_id TEXT,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS thumbnails ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    asset_id INTEGER,"
    "    thumb_path TEXT,"
    "    w INTEGER,"
    "    h INTEGER,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS imports ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    path TEXT,"
    "    kind TEXT,"
    "    processed INTEGER DEFAULT 0,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS providers ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    name TEXT,"
    "    type TEXT,"
    "    config JSON,"
    "    active INTEGER DEFAULT 1,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS gpu_nodes ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    name TEXT,"
    "    type TEXT,"
    "    host TEXT,"
    "    api TEXT,"
    "    creds_ref TEXT,"
    "    capacity JSON,"
    "    active INTEGER DEFAULT 1,"
    "    meta JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS jobs ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    type TEXT,"
    "    status TEXT,"
    "    submit_ts TEXT DEFAULT CURRENT_TIMESTAMP,"
    "    done_ts TEXT,"
    "    owner TEXT,"
    "    input_json JSON,"
    "    output_json JSON,"
    "    logs_path TEXT"
    ");",
    "CREATE TABLE IF NOT EXISTS translations ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    scene_id INTEGER,"
    "    lang TEXT,"
    "    body JSON,"
    "    confidence REAL,"
    "    src_lang TEXT,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
    "CREATE TABLE IF NOT EXISTS settings ("
    "    id INTEGER PRIMARY KEY,"
    "    project_id TEXT DEFAULT 'default',"
    "    key TEXT,"
    "    value JSON,"
    "    created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");",
]


COLUMN_PATCHES = {
    "scenes": [("project_id", "TEXT DEFAULT 'default'")],
    "characters": [("project_id", "TEXT DEFAULT 'default'")],
    "timelines": [("project_id", "TEXT DEFAULT 'default'")],
    "worlds": [("project_id", "TEXT DEFAULT 'default'")],
    "assets_registry": [
        ("project_id", "TEXT DEFAULT 'default'"),
        ("path_thumb", "TEXT"),
        ("hash", "TEXT"),
        ("bytes", "INTEGER"),
        ("meta", "JSON"),
    ],
    "provenance": [("project_id", "TEXT DEFAULT 'default'")],
    "thumbnails": [("project_id", "TEXT DEFAULT 'default'")],
    "imports": [("project_id", "TEXT DEFAULT 'default'"), ("processed", "INTEGER DEFAULT 0")],
    "gpu_nodes": [("project_id", "TEXT DEFAULT 'default'")],
    "jobs": [("project_id", "TEXT DEFAULT 'default'")],
    "translations": [("project_id", "TEXT DEFAULT 'default'")],
    "templates": [("project_id", "TEXT DEFAULT 'default'")],
    "variables": [("project_id", "TEXT DEFAULT 'default'")],
    "providers": [("project_id", "TEXT DEFAULT 'default'")],
    "settings": [("project_id", "TEXT DEFAULT 'default'")],
}


def ensure_dirs() -> None:
    for directory in DIRS:
        directory.mkdir(parents=True, exist_ok=True)


def ensure_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        for statement in SCHEMA:
            cur.execute(statement)
        for table, patches in COLUMN_PATCHES.items():
            existing_cols = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
            for col_name, ddl in patches:
                if col_name not in existing_cols:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {ddl}")
        con.commit()
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild phase-06 directories and database.")
    parser.add_argument("--recreate-all", action="store_true", help="Recreate required folders and tables.")
    args = parser.parse_args()
    if args.recreate_all:
        ensure_dirs()
        ensure_db()
        print(f"[v0.6] ✅ Recreated folders and DB at: {DB_PATH}")
    else:
        print("Nothing to do. Use --recreate-all")


if __name__ == "__main__":
    main()
