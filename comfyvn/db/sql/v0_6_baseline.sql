-- ComfyVN schema baseline (v0.6)
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    body_json TEXT,
    meta_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    traits_json TEXT,
    portrait_asset_id INTEGER,
    meta_json TEXT,
    FOREIGN KEY (portrait_asset_id) REFERENCES assets_registry(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS timelines (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    scene_order_json TEXT,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS variables (
    id INTEGER PRIMARY KEY,
    scope TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    value_json TEXT
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    payload_json TEXT,
    type TEXT,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS assets_registry (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    path TEXT NOT NULL,
    hash TEXT,
    bytes INTEGER,
    meta_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS thumbnails (
    asset_id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    w INTEGER NOT NULL,
    h INTEGER NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets_registry(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS provenance (
    asset_id INTEGER PRIMARY KEY,
    seed TEXT,
    tool TEXT,
    workflow TEXT,
    "commit" TEXT,
    meta_json TEXT,
    FOREIGN KEY (asset_id) REFERENCES assets_registry(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    logs_path TEXT,
    in_json TEXT,
    out_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL DEFAULT 0,
    meta_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS providers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    config_json TEXT,
    status_json TEXT
);

CREATE TABLE IF NOT EXISTS translations (
    id INTEGER PRIMARY KEY,
    target_id INTEGER NOT NULL,
    lang TEXT NOT NULL,
    body_json TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT
);
