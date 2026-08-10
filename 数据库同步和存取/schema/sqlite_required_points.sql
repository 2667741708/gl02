PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 10000;

CREATE TABLE IF NOT EXISTS user_instructions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS sensor_registry (
    variable_name TEXT PRIMARY KEY,
    chinese_name TEXT NOT NULL,
    branch TEXT NOT NULL,
    short_name TEXT NOT NULL,
    tag_long_name TEXT NOT NULL,
    description TEXT NOT NULL,
    status_usage TEXT NOT NULL,
    is_derived INTEGER NOT NULL DEFAULT 0,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sensor_registry_tag
    ON sensor_registry(tag_long_name)
    WHERE is_derived = 0;

CREATE TABLE IF NOT EXISTS one_minute_values (
    tag_long_name TEXT NOT NULL,
    ts TEXT NOT NULL,
    value REAL,
    quality TEXT,
    value_type INTEGER,
    aggregate TEXT NOT NULL DEFAULT 'PS_HIS_AVERAGE',
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    source_server TEXT NOT NULL DEFAULT '10.22.181.243:8889',
    collected_at TEXT NOT NULL,
    PRIMARY KEY (tag_long_name, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_one_minute_values_ts
    ON one_minute_values(ts);

CREATE INDEX IF NOT EXISTS idx_one_minute_values_tag_ts_desc
    ON one_minute_values(tag_long_name, ts DESC);

CREATE TABLE IF NOT EXISTS sync_state (
    tag_long_name TEXT PRIMARY KEY,
    last_success_ts TEXT,
    last_attempt_ts TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    mode TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    requested_tags INTEGER NOT NULL DEFAULT 0,
    inserted_rows INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error TEXT
);
