from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from catalog import SensorPoint, load_config


MODULE_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODULE_DIR.parents[0]
WORKSPACE_ROOT = ROOT_DIR.parents[0]
DEFAULT_CONFIG = ROOT_DIR / "config" / "sync_config.json"


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return WORKSPACE_ROOT / path


def default_db_path(config_path: str | Path = DEFAULT_CONFIG) -> Path:
    config = load_config(config_path)
    return resolve_project_path(config["database"]["local_demo_path"])


def default_schema_path(config_path: str | Path = DEFAULT_CONFIG) -> Path:
    config = load_config(config_path)
    return resolve_project_path(config["database"]["schema_sql"])


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(db_path: str | Path | None = None, config_path: str | Path = DEFAULT_CONFIG) -> sqlite3.Connection:
    resolved = Path(db_path) if db_path else default_db_path(config_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection, config_path: str | Path = DEFAULT_CONFIG) -> None:
    conn.executescript(default_schema_path(config_path).read_text(encoding="utf-8"))
    conn.commit()


def upsert_registry(conn: sqlite3.Connection, points: list[SensorPoint]) -> None:
    rows = [
        (
            point.variable_name,
            point.chinese_name,
            point.branch,
            point.short_name,
            point.tag_long_name,
            point.description,
            point.status_usage,
            1 if point.is_derived else 0,
            1,
            now_text(),
        )
        for point in points
    ]
    conn.executemany(
        """
        INSERT INTO sensor_registry (
            variable_name, chinese_name, branch, short_name, tag_long_name,
            description, status_usage, is_derived, is_enabled, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(variable_name) DO UPDATE SET
            chinese_name=excluded.chinese_name,
            branch=excluded.branch,
            short_name=excluded.short_name,
            tag_long_name=excluded.tag_long_name,
            description=excluded.description,
            status_usage=excluded.status_usage,
            is_derived=excluded.is_derived,
            is_enabled=excluded.is_enabled,
            updated_at=excluded.updated_at
        """,
        rows,
    )
    conn.commit()


def insert_instruction(conn: sqlite3.Connection, title: str, content: str, source_file: str = "") -> None:
    existing = conn.execute(
        "SELECT id FROM user_instructions WHERE title = ? AND content = ?",
        (title, content),
    ).fetchone()
    if existing:
        return
    conn.execute(
        "INSERT INTO user_instructions (created_at, title, content, source_file) VALUES (?, ?, ?, ?)",
        (now_text(), title, content, source_file),
    )
    conn.commit()


def upsert_values(
    conn: sqlite3.Connection,
    series_by_tag: dict[str, dict[str, float | None]],
    source_server: str,
    aggregate: str = "PS_HIS_AVERAGE",
    interval_seconds: int = 60,
) -> int:
    rows: list[tuple[Any, ...]] = []
    collected_at = now_text()
    for tag, series in series_by_tag.items():
        for ts, value in series.items():
            rows.append((tag, ts, value, None, None, aggregate, interval_seconds, source_server, collected_at))
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT OR REPLACE INTO one_minute_values (
            tag_long_name, ts, value, quality, value_type,
            aggregate, interval_seconds, source_server, collected_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def update_sync_state(conn: sqlite3.Connection, tags: list[str], success_ts: str | None, errors: dict[str, str]) -> None:
    rows = []
    attempted = now_text()
    for tag in tags:
        error = errors.get(tag, "")
        rows.append((tag, None if error else success_ts, attempted, error, attempted))
    conn.executemany(
        """
        INSERT INTO sync_state (tag_long_name, last_success_ts, last_attempt_ts, last_error, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tag_long_name) DO UPDATE SET
            last_success_ts=COALESCE(excluded.last_success_ts, sync_state.last_success_ts),
            last_attempt_ts=excluded.last_attempt_ts,
            last_error=excluded.last_error,
            updated_at=excluded.updated_at
        """,
        rows,
    )
    conn.commit()


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    data = conn.execute(
        """
        SELECT COUNT(*) AS rows_count,
               COUNT(DISTINCT tag_long_name) AS tag_count,
               MIN(ts) AS min_ts,
               MAX(ts) AS max_ts
        FROM one_minute_values
        """
    ).fetchone()
    registry = conn.execute("SELECT COUNT(*) AS n FROM sensor_registry WHERE is_enabled=1").fetchone()
    physical = conn.execute("SELECT COUNT(*) AS n FROM sensor_registry WHERE is_enabled=1 AND is_derived=0").fetchone()
    instructions = conn.execute("SELECT COUNT(*) AS n FROM user_instructions").fetchone()
    return {
        "registry_enabled": int(registry["n"] or 0),
        "physical_points": int(physical["n"] or 0),
        "rows": int(data["rows_count"] or 0),
        "tags_with_data": int(data["tag_count"] or 0),
        "min_ts": data["min_ts"],
        "max_ts": data["max_ts"],
        "instructions": int(instructions["n"] or 0),
    }
