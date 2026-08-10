from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from catalog import SensorPoint, load_config


MODULE_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODULE_DIR.parents[0]
WORKSPACE_ROOT = ROOT_DIR.parents[0]
DEFAULT_CONFIG = ROOT_DIR / "config" / "sync_config.json"


def env_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    if os.name != "nt":
        return default
    try:
        import winreg

        for root, path in (
            (winreg.HKEY_CURRENT_USER, "Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(root, path) as key:
                    value, _ = winreg.QueryValueEx(key, name)
                    if value:
                        return str(value)
            except OSError:
                continue
    except Exception:
        return default
    return default


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return WORKSPACE_ROOT / path


def pg_config(config_path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    pg = config["database"]["postgresql"]
    return {
        "host": env_value("GL02_PGHOST", str(pg.get("host", "10.30.220.12"))),
        "port": int(env_value("GL02_PGPORT", str(pg.get("port", 5432)))),
        "dbname": env_value("GL02_PGDATABASE", str(pg.get("database", "bf_trend"))),
        "user": env_value("GL02_PGUSER", str(pg.get("user", ""))),
        "password": env_value("GL02_PGPASSWORD", str(pg.get("password", ""))),
        "connect_timeout": int(env_value("GL02_PGCONNECT_TIMEOUT", str(pg.get("connect_timeout_seconds", 10)))),
    }


def schema_path(config_path: str | Path = DEFAULT_CONFIG) -> Path:
    config = load_config(config_path)
    return resolve_project_path(config["database"]["postgresql"]["schema_sql"])


def now_dt() -> datetime:
    return datetime.now().replace(microsecond=0)


def connect(config_path: str | Path = DEFAULT_CONFIG) -> psycopg.Connection:
    params = pg_config(config_path)
    if not params["user"]:
        raise RuntimeError("PostgreSQL user is not configured. Set GL02_PGUSER and GL02_PGPASSWORD.")
    return psycopg.connect(**params, row_factory=dict_row)


def ensure_schema(conn: psycopg.Connection, config_path: str | Path = DEFAULT_CONFIG) -> None:
    conn.execute(schema_path(config_path).read_text(encoding="utf-8"))
    conn.commit()


def ensure_partitions(conn: psycopg.Connection, start: datetime, end: datetime) -> None:
    conn.execute("SELECT bf_sensor.ensure_1min_partitions(%s, %s)", (start, end))
    conn.commit()


def ensure_raw_5s_partitions(conn: psycopg.Connection, start: datetime, end: datetime) -> None:
    conn.execute("SELECT bf_sensor.ensure_raw_5s_partitions(%s, %s)", (start, end))
    conn.commit()


def apply_retention(conn: psycopg.Connection, retain_years: int = 3) -> int:
    row = conn.execute(
        "SELECT bf_sensor.drop_1min_partitions_older_than((%s || ' years')::interval) AS dropped",
        (retain_years,),
    ).fetchone()
    conn.commit()
    return int(row["dropped"] if row else 0)


def apply_raw_5s_retention(conn: psycopg.Connection, retain_days: int = 30) -> int:
    row = conn.execute(
        "SELECT bf_sensor.drop_raw_5s_partitions_older_than((%s || ' days')::interval) AS dropped",
        (retain_days,),
    ).fetchone()
    conn.commit()
    return int(row["dropped"] if row else 0)


def upsert_registry(conn: psycopg.Connection, points: list[SensorPoint]) -> None:
    rows = [
        (
            point.variable_name,
            point.chinese_name,
            point.branch,
            point.short_name,
            point.tag_long_name,
            point.description,
            point.status_usage,
            point.is_derived,
            True,
            now_dt(),
        )
        for point in points
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO bf_sensor.sensor_registry (
                variable_name, chinese_name, branch, short_name, tag_long_name,
                description, status_usage, is_derived, is_enabled, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


def insert_instruction(conn: psycopg.Connection, title: str, content: str, source_file: str = "") -> None:
    conn.execute(
        """
        INSERT INTO bf_sensor.user_instructions (created_at, title, content, source_file)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT(title, content) DO NOTHING
        """,
        (now_dt(), title, content, source_file),
    )
    conn.commit()


def start_run(conn: psycopg.Connection, sync_mode: str, start_ts: datetime, end_ts: datetime) -> int:
    row = conn.execute(
        """
        INSERT INTO bf_sensor.sync_runs (sync_mode, start_ts, end_ts)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (sync_mode, start_ts, end_ts),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    rows_written: int,
    tags_ok: int,
    tags_error: int,
    error: str = "",
) -> None:
    conn.execute(
        """
        UPDATE bf_sensor.sync_runs
        SET finished_at=%s, rows_written=%s, tags_ok=%s, tags_error=%s, error=%s
        WHERE id=%s
        """,
        (now_dt(), rows_written, tags_ok, tags_error, error, run_id),
    )
    conn.commit()


def latest_values_before(
    conn: psycopg.Connection,
    tags: list[str],
    before: datetime,
    *,
    maximum_lookback_minutes: int,
) -> dict[str, tuple[datetime, float]]:
    if not tags or maximum_lookback_minutes <= 0:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON(tag_long_name) tag_long_name,ts,value
            FROM bf_sensor.one_minute_values
            WHERE tag_long_name=ANY(%s) AND ts<%s
              AND ts>=%s-(%s * interval '1 minute') AND value IS NOT NULL
            ORDER BY tag_long_name,ts DESC
            """,
            (tags, before, before, int(maximum_lookback_minutes)),
        )
        return {
            str(row["tag_long_name"]): (row["ts"], float(row["value"]))
            for row in cur.fetchall()
        }


def upsert_values(
    conn: psycopg.Connection,
    series_by_tag: dict[str, dict[str, float | None]],
    source_server: str,
    aggregate: str = "PS_HIS_AVERAGE",
    interval_seconds: int = 60,
    audit_by_tag: dict[str, dict[str, dict[str, Any]]] | None = None,
    semantic_version: str = "",
) -> int:
    rows: list[tuple[Any, ...]] = []
    collected_at = now_dt()
    for tag, series in series_by_tag.items():
        for ts, value in series.items():
            audit = (audit_by_tag or {}).get(tag, {}).get(ts, {})
            rows.append(
                (
                    tag,
                    ts,
                    value,
                    audit.get("quality"),
                    None,
                    audit.get("aggregate") or aggregate,
                    interval_seconds,
                    source_server,
                    collected_at,
                    audit.get("sample_count"),
                    audit.get("numeric_sample_count"),
                    audit.get("good_sample_count"),
                    audit.get("expected_sample_count"),
                    audit.get("coverage_ratio"),
                    audit.get("min_value"),
                    audit.get("max_value"),
                    audit.get("last_value"),
                    audit.get("window_complete"),
                    audit.get("semantic_version") or semantic_version or None,
                )
            )
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO bf_sensor.one_minute_values (
                tag_long_name, ts, value, quality, value_type,
                aggregate, interval_seconds, source_server, collected_at,
                sample_count, numeric_sample_count, good_sample_count,
                expected_sample_count, coverage_ratio,
                min_value, max_value, last_value, window_complete, semantic_version
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT(tag_long_name, ts) DO UPDATE SET
                value=excluded.value,
                quality=excluded.quality,
                value_type=excluded.value_type,
                aggregate=excluded.aggregate,
                interval_seconds=excluded.interval_seconds,
                source_server=excluded.source_server,
                collected_at=excluded.collected_at,
                sample_count=excluded.sample_count,
                numeric_sample_count=excluded.numeric_sample_count,
                good_sample_count=excluded.good_sample_count,
                expected_sample_count=excluded.expected_sample_count,
                coverage_ratio=excluded.coverage_ratio,
                min_value=excluded.min_value,
                max_value=excluded.max_value,
                last_value=excluded.last_value,
                window_complete=excluded.window_complete,
                semantic_version=excluded.semantic_version
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def upsert_raw_5s_values(
    conn: psycopg.Connection,
    rows: list[tuple[Any, ...]],
) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO bf_sensor.raw_5s_values (
                tag_long_name, ts, value, quality, value_type,
                raw_interval_seconds, source_server, read_start_ts, read_end_ts, collected_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(tag_long_name, ts) DO UPDATE SET
                value=excluded.value,
                quality=excluded.quality,
                value_type=excluded.value_type,
                raw_interval_seconds=excluded.raw_interval_seconds,
                source_server=excluded.source_server,
                read_start_ts=excluded.read_start_ts,
                read_end_ts=excluded.read_end_ts,
                collected_at=excluded.collected_at
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def update_sync_state(
    conn: psycopg.Connection,
    tags: list[str],
    success_ts: datetime | None,
    errors: dict[str, str],
) -> None:
    attempted = now_dt()
    rows = []
    for tag in tags:
        error = errors.get(tag, "")
        rows.append((tag, None if error else success_ts, attempted, error, attempted))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO bf_sensor.sync_state (tag_long_name, last_success_ts, last_attempt_ts, last_error, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(tag_long_name) DO UPDATE SET
                last_success_ts=COALESCE(excluded.last_success_ts, bf_sensor.sync_state.last_success_ts),
                last_attempt_ts=excluded.last_attempt_ts,
                last_error=excluded.last_error,
                updated_at=excluded.updated_at
            """,
            rows,
        )
    conn.commit()


def summary(conn: psycopg.Connection) -> dict[str, Any]:
    data = conn.execute(
        """
        SELECT COUNT(*) AS rows_count,
               COUNT(DISTINCT tag_long_name) AS tag_count,
               MIN(ts) AS min_ts,
               MAX(ts) AS max_ts
        FROM bf_sensor.one_minute_values
        """
    ).fetchone()
    registry = conn.execute("SELECT COUNT(*) AS n FROM bf_sensor.sensor_registry WHERE is_enabled=true").fetchone()
    physical = conn.execute(
        "SELECT COUNT(*) AS n FROM bf_sensor.sensor_registry WHERE is_enabled=true AND is_derived=false"
    ).fetchone()
    instructions = conn.execute("SELECT COUNT(*) AS n FROM bf_sensor.user_instructions").fetchone()
    return {
        "registry_enabled": int(registry["n"] or 0),
        "physical_points": int(physical["n"] or 0),
        "rows": int(data["rows_count"] or 0),
        "tags_with_data": int(data["tag_count"] or 0),
        "min_ts": str(data["min_ts"]) if data["min_ts"] else None,
        "max_ts": str(data["max_ts"]) if data["max_ts"] else None,
        "instructions": int(instructions["n"] or 0),
    }


def raw_5s_summary(conn: psycopg.Connection) -> dict[str, Any]:
    data = conn.execute(
        """
        SELECT COUNT(*) AS rows_count,
               COUNT(DISTINCT tag_long_name) AS tag_count,
               MIN(ts) AS min_ts,
               MAX(ts) AS max_ts
        FROM bf_sensor.raw_5s_values
        """
    ).fetchone()
    return {
        "rows": int(data["rows_count"] or 0),
        "tags_with_data": int(data["tag_count"] or 0),
        "min_ts": str(data["min_ts"]) if data["min_ts"] else None,
        "max_ts": str(data["max_ts"]) if data["max_ts"] else None,
    }
