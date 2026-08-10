from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from collections.abc import Mapping
from typing import Any


REQUIRED_AUDIT_COLUMNS = {
    "sample_count",
    "numeric_sample_count",
    "good_sample_count",
    "expected_sample_count",
    "coverage_ratio",
    "min_value",
    "max_value",
    "last_value",
    "window_complete",
    "semantic_version",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the 220.12 pSpace minute-average cutover.")
    parser.add_argument("--project-root", required=True)
    return parser.parse_args()


def rows(cursor, sql: str) -> list[dict[str, Any]]:
    cursor.execute(sql)
    fetched = cursor.fetchall()
    if fetched and isinstance(fetched[0], Mapping):
        return [dict(row) for row in fetched]
    names = [item.name for item in cursor.description]
    return [dict(zip(names, row)) for row in fetched]


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root)
    sync_root = project_root / "数据库同步和存取"
    sys.path.insert(0, str(sync_root / "src"))
    import pg_store

    conn = pg_store.connect(sync_root / "config" / "sync_config.json")
    try:
        with conn.cursor() as cursor:
            column_rows = rows(
                cursor,
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'bf_sensor' AND table_name = 'one_minute_values'
                """,
            )
            columns = {str(row["column_name"]) for row in column_rows}
            recent = rows(
                cursor,
                """
                SELECT aggregate,
                       COALESCE(semantic_version, '') AS semantic_version,
                       window_complete,
                       count(*) AS rows,
                       count(DISTINCT tag_long_name) AS tags,
                       min(ts) AS min_ts,
                       max(ts) AS max_ts,
                       min(sample_count) AS min_samples,
                       max(sample_count) AS max_samples,
                       min(coverage_ratio) AS min_coverage,
                       max(coverage_ratio) AS max_coverage
                FROM bf_sensor.one_minute_values
                WHERE ts >= now() - interval '20 minutes'
                GROUP BY aggregate, semantic_version, window_complete
                ORDER BY max(ts) DESC, aggregate, semantic_version, window_complete
                """,
            )
            raw = rows(
                cursor,
                """
                SELECT count(*) AS rows,
                       count(DISTINCT tag_long_name) AS tags,
                       min(ts) AS min_ts,
                       max(ts) AS max_ts,
                       count(*) FILTER (WHERE value IS NOT NULL) AS numeric_rows
                FROM bf_sensor.raw_5s_values
                WHERE ts >= now() - interval '20 minutes'
                """,
            )[0]
            comparison = rows(
                cursor,
                """
                WITH raw_mean AS (
                    SELECT tag_long_name,
                           date_trunc('minute', ts) AS minute_ts,
                           avg(value) AS raw_mean,
                           count(*) AS raw_good_count
                    FROM bf_sensor.raw_5s_values
                    WHERE ts >= now() - interval '15 minutes'
                      AND value IS NOT NULL
                      AND (
                          quality IS NULL OR btrim(quality) = '' OR quality = '192'
                          OR lower(quality) LIKE 'good%'
                      )
                    GROUP BY tag_long_name, date_trunc('minute', ts)
                ), compared AS (
                    SELECT v.tag_long_name,
                           v.ts,
                           v.value AS stored_mean,
                           r.raw_mean,
                           abs(v.value - r.raw_mean) AS delta,
                           v.good_sample_count,
                           r.raw_good_count,
                           v.window_complete
                    FROM bf_sensor.one_minute_values v
                    JOIN raw_mean r
                      ON r.tag_long_name = v.tag_long_name
                     AND r.minute_ts = v.ts
                    WHERE v.ts >= now() - interval '15 minutes'
                      AND v.aggregate = 'PS_RAW_AVERAGE'
                      AND v.semantic_version = 'valid_raw_mean_v1'
                )
                SELECT count(*) AS compared_rows,
                       count(*) FILTER (WHERE delta > 1e-9) AS mismatch_rows,
                       max(delta) AS max_delta,
                       count(*) FILTER (WHERE good_sample_count <> raw_good_count) AS count_mismatches,
                       count(*) FILTER (WHERE window_complete) AS complete_rows,
                       count(*) FILTER (WHERE NOT window_complete) AS open_rows,
                       max(ts) AS max_ts
                FROM compared
                """,
            )[0]
            sync_runs = rows(
                cursor,
                """
                SELECT id, started_at, finished_at, sync_mode, start_ts, end_ts,
                       rows_written, tags_ok, tags_error, error
                FROM bf_sensor.sync_runs
                ORDER BY id DESC
                LIMIT 6
                """,
            )
            legacy = rows(
                cursor,
                """
                SELECT aggregate, count(*) AS rows, max(ts) AS max_ts
                FROM bf_sensor.one_minute_values
                WHERE ts < now() - interval '20 minutes'
                  AND ts >= now() - interval '24 hours'
                GROUP BY aggregate
                ORDER BY aggregate
                """,
            )
    finally:
        conn.close()

    newest_average = max(
        (
            row["max_ts"]
            for row in recent
            if row["aggregate"] == "PS_RAW_AVERAGE" and row["max_ts"] is not None
        ),
        default=None,
    )
    latest_lag_seconds = None
    if isinstance(newest_average, datetime):
        latest_lag_seconds = round((datetime.now() - newest_average).total_seconds(), 3)

    ok = (
        not (REQUIRED_AUDIT_COLUMNS - columns)
        and any(row["aggregate"] == "PS_RAW_AVERAGE" for row in recent)
        and int(raw["rows"] or 0) > 0
        and int(comparison["compared_rows"] or 0) > 0
        and int(comparison["mismatch_rows"] or 0) == 0
        and int(comparison["count_mismatches"] or 0) == 0
        and latest_lag_seconds is not None
        and latest_lag_seconds < 300
    )
    payload = {
        "ok": ok,
        "checked_at": datetime.now(),
        "missing_audit_columns": sorted(REQUIRED_AUDIT_COLUMNS - columns),
        "latest_average_lag_seconds": latest_lag_seconds,
        "recent_minute_groups": recent,
        "recent_raw": raw,
        "raw_mean_comparison": comparison,
        "recent_sync_runs": sync_runs,
        "legacy_last_24h": legacy,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
