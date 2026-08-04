# -*- coding: utf-8 -*-
"""Audit 220.12 PostgreSQL 1min coverage against 243 pSpace raw history.

Run on 10.30.220.12. The script is read-only for pSpace and only reads
PostgreSQL. It writes JSON/CSV reports under logs/.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SYNC_ROOT = ROOT / "数据库同步和存取"
SYNC_SRC = SYNC_ROOT / "src"
TREND_BACKEND = ROOT / "趋势分析" / "trend_backend"
LOG_DIR = ROOT / "logs"

for path in (SYNC_SRC, TREND_BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pg_store import connect  # noqa: E402
import pspace_history  # noqa: E402


TOP_D_TAG = r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0043"
TOP_TAGS = {
    "T_top_A": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0040",
    "T_top_B": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0064",
    "T_top_C": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0072",
    "T_top_D": TOP_D_TAG,
}


def text_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def minute_floor(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def minute_range(start: datetime, end: datetime) -> list[datetime]:
    result = []
    current = minute_floor(start)
    end = minute_floor(end)
    while current <= end:
        result.append(current)
        current += timedelta(minutes=1)
    return result


def percentile(values: list[int], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    lo = int(index)
    hi = min(lo + 1, len(ordered) - 1)
    frac = index - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def db_window_and_registry(conn, hours: float) -> tuple[datetime, datetime, list[dict[str, Any]]]:
    bounds = conn.execute(
        """
        SELECT min(ts) AS min_ts, max(ts) AS max_ts
          FROM bf_sensor.one_minute_values
        """
    ).fetchone()
    if not bounds or not bounds["max_ts"]:
        raise RuntimeError("bf_sensor.one_minute_values has no data")
    end = minute_floor(bounds["max_ts"])
    start = end - timedelta(hours=hours)
    registry = conn.execute(
        """
        SELECT variable_name, tag_long_name
          FROM bf_sensor.sensor_registry
         WHERE is_enabled = true
           AND is_derived = false
         ORDER BY variable_name
        """
    ).fetchall()
    return start, end, [dict(row) for row in registry]


def query_db_coverage(conn, start: datetime, end: datetime, registry: list[dict[str, Any]]) -> dict[str, Any]:
    tags = [row["tag_long_name"] for row in registry]
    expected_minutes = len(minute_range(start, end))
    expected_tags = len(tags)

    tag_rows = conn.execute(
        """
        WITH expected AS (
          SELECT unnest(%s::text[]) AS tag_long_name
        ),
        agg AS (
          SELECT tag_long_name,
                 count(*) AS row_count,
                 count(value) AS non_null_count,
                 count(*) FILTER (WHERE value IS NULL) AS null_count,
                 min(ts) AS min_ts,
                 max(ts) AS max_ts
            FROM bf_sensor.one_minute_values
           WHERE ts >= %s
             AND ts <= %s
             AND tag_long_name = ANY(%s)
           GROUP BY tag_long_name
        )
        SELECT e.tag_long_name,
               coalesce(a.row_count, 0) AS row_count,
               coalesce(a.non_null_count, 0) AS non_null_count,
               coalesce(a.null_count, 0) AS null_count,
               a.min_ts,
               a.max_ts
          FROM expected e
          LEFT JOIN agg a USING(tag_long_name)
         ORDER BY e.tag_long_name
        """,
        (tags, start, end, tags),
    ).fetchall()

    by_tag = {row["tag_long_name"]: row for row in registry}
    tag_coverage = []
    for row in tag_rows:
        meta = by_tag.get(row["tag_long_name"], {})
        row_count = int(row["row_count"] or 0)
        null_count = int(row["null_count"] or 0)
        tag_coverage.append(
            {
                "variable_name": meta.get("variable_name", ""),
                "tag_long_name": row["tag_long_name"],
                "expected_minutes": expected_minutes,
                "row_count": row_count,
                "missing_rows": max(expected_minutes - row_count, 0),
                "null_rows": null_count,
                "effective_missing_rows": max(expected_minutes - row_count, 0) + null_count,
                "min_ts": text_time(row["min_ts"]),
                "max_ts": text_time(row["max_ts"]),
            }
        )

    minute_rows = conn.execute(
        """
        WITH minutes AS (
          SELECT generate_series(%s::timestamp, %s::timestamp, interval '1 minute') AS ts
        )
        SELECT m.ts,
               count(v.tag_long_name) AS present_rows,
               count(v.value) AS non_null_rows,
               count(*) FILTER (WHERE v.value IS NULL AND v.tag_long_name IS NOT NULL) AS null_rows
          FROM minutes m
          LEFT JOIN bf_sensor.one_minute_values v
            ON v.ts = m.ts
           AND v.tag_long_name = ANY(%s)
         GROUP BY m.ts
         ORDER BY m.ts
        """,
        (start, end, tags),
    ).fetchall()

    problem_minutes = []
    for row in minute_rows:
        present = int(row["present_rows"] or 0)
        non_null = int(row["non_null_rows"] or 0)
        null_rows = int(row["null_rows"] or 0)
        if present < expected_tags or non_null < expected_tags:
            problem_minutes.append(
                {
                    "ts": text_time(row["ts"]),
                    "present_rows": present,
                    "non_null_rows": non_null,
                    "null_rows": null_rows,
                    "missing_tags": expected_tags - present,
                    "effective_missing_tags": expected_tags - non_null,
                }
            )

    top_d_missing = conn.execute(
        """
        WITH minutes AS (
          SELECT generate_series(%s::timestamp, %s::timestamp, interval '1 minute') AS ts
        )
        SELECT m.ts,
               CASE WHEN v.ts IS NULL THEN true ELSE false END AS row_missing,
               CASE WHEN v.ts IS NOT NULL AND v.value IS NULL THEN true ELSE false END AS value_null
          FROM minutes m
          LEFT JOIN bf_sensor.one_minute_values v
            ON v.ts = m.ts
           AND v.tag_long_name = %s
         WHERE v.ts IS NULL OR v.value IS NULL
         ORDER BY m.ts
        """,
        (start, end, TOP_D_TAG),
    ).fetchall()

    return {
        "expected_tags": expected_tags,
        "expected_minutes": expected_minutes,
        "expected_total_rows": expected_tags * expected_minutes,
        "tag_coverage": tag_coverage,
        "worst_tags": sorted(tag_coverage, key=lambda item: item["effective_missing_rows"], reverse=True)[:20],
        "problem_minute_count": len(problem_minutes),
        "problem_minutes_first_50": problem_minutes[:50],
        "problem_minutes_last_50": problem_minutes[-50:],
        "top_d_missing_count": len(top_d_missing),
        "top_d_missing_first_50": [
            {"ts": text_time(row["ts"]), "row_missing": bool(row["row_missing"]), "value_null": bool(row["value_null"])}
            for row in top_d_missing[:50]
        ],
        "top_d_missing_last_50": [
            {"ts": text_time(row["ts"]), "row_missing": bool(row["row_missing"]), "value_null": bool(row["value_null"])}
            for row in top_d_missing[-50:]
        ],
    }


def parse_raw_records(result: dict[str, Any], T, tag: str) -> list[dict[str, Any]]:
    records = result.get(tag, {})
    rows: list[dict[str, Any]] = []
    if not isinstance(records, dict):
        return rows
    for _, record in pspace_history.numeric_items(records):
        if not isinstance(record, dict):
            continue
        ts = pspace_history.parse_timestamp(record.get(T.HisReadRawTimeStamp))
        if ts is None:
            continue
        rows.append(
            {
                "ts": ts,
                "value": pspace_history.coerce_number(record.get(T.HisReadRawValueDict)),
                "quality": str(record.get(T.HisReadRawQualityDict, "") or ""),
                "value_type": str(record.get(T.ReadTypeDict, "") or ""),
            }
        )
    rows.sort(key=lambda item: item["ts"])
    return rows


def parse_processed_records(result: dict[str, Any], T, tag: str) -> list[dict[str, Any]]:
    series, qualities, errors = pspace_history.parse_processed_result(result, T, [tag])
    rows = []
    for ts_text, value in sorted(series.get(tag, {}).items()):
        parsed = pspace_history.parse_timestamp(ts_text)
        rows.append({"ts": parsed, "value": value})
    return rows


def pspace_raw_and_processed(start: datetime, end: datetime) -> dict[str, Any]:
    config_candidates = [
        ROOT / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        ROOT / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
    ]
    config_path = next((path for path in config_candidates if path.exists()), config_candidates[-1])
    connection = pspace_history.resolve_connection(config_path=config_path, server="10.22.181.243", port="8889")
    PsObject, T = pspace_history.load_sdk(ROOT / "pythonSDK(1)")
    pspace = pspace_history.connect_pspace(PsObject, T, connection)
    try:
        raw_result = pspace.HisReadRaw(
            {
                T.HisReadRawTagLongName: [TOP_D_TAG],
                T.HisReadRawstartTime: pspace_history.format_ps_time(start),
                T.HisReadRawendTime: pspace_history.format_ps_time(end),
                T.HisReadRawMaxValues: 20000,
                T.HisReadRawBounds: 0,
            }
        )
        processed_result = pspace_history.read_processed_batch(pspace, T, [TOP_D_TAG], start, end, 60, "PS_HIS_AVERAGE")
    finally:
        pspace_history.close_pspace(pspace)

    raw_rows = parse_raw_records(raw_result, T, TOP_D_TAG)
    processed_rows = parse_processed_records(processed_result, T, TOP_D_TAG)
    minutes = minute_range(start, end)
    raw_by_minute: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        raw_by_minute[minute_floor(row["ts"])].append(row)

    raw_counts = [len(raw_by_minute.get(minute, [])) for minute in minutes]
    raw_problem_minutes = []
    for minute in minutes:
        rows = raw_by_minute.get(minute, [])
        if len(rows) < 12 or any(row["value"] is None for row in rows):
            raw_problem_minutes.append(
                {
                    "minute": text_time(minute),
                    "raw_count": len(rows),
                    "null_value_count": sum(1 for row in rows if row["value"] is None),
                    "qualities": dict(Counter(row["quality"] for row in rows)),
                }
            )

    processed_by_minute = {minute_floor(row["ts"]): row for row in processed_rows if row.get("ts") is not None}
    processed_missing = [minute for minute in minutes if minute not in processed_by_minute or processed_by_minute[minute].get("value") is None]

    return {
        "tag": TOP_D_TAG,
        "start": text_time(start),
        "end": text_time(end),
        "expected_minutes": len(minutes),
        "raw_total_rows": len(raw_rows),
        "raw_count_distribution": dict(Counter(raw_counts)),
        "raw_min_per_minute": min(raw_counts) if raw_counts else None,
        "raw_max_per_minute": max(raw_counts) if raw_counts else None,
        "raw_avg_per_minute": round(sum(raw_counts) / len(raw_counts), 3) if raw_counts else None,
        "raw_p50_per_minute": percentile(raw_counts, 0.5),
        "raw_p95_per_minute": percentile(raw_counts, 0.95),
        "raw_minutes_below_12": sum(1 for count in raw_counts if count < 12),
        "raw_zero_minutes": sum(1 for count in raw_counts if count == 0),
        "raw_problem_minutes_first_50": raw_problem_minutes[:50],
        "raw_problem_minutes_last_50": raw_problem_minutes[-50:],
        "processed_rows": len(processed_rows),
        "processed_missing_minutes": len(processed_missing),
        "processed_missing_first_50": [text_time(minute) for minute in processed_missing[:50]],
        "processed_missing_last_50": [text_time(minute) for minute in processed_missing[-50:]],
        "raw_first_ts": str(raw_rows[0]["ts"]) if raw_rows else None,
        "raw_last_ts": str(raw_rows[-1]["ts"]) if raw_rows else None,
        "processed_first_ts": str(processed_rows[0]["ts"]) if processed_rows else None,
        "processed_last_ts": str(processed_rows[-1]["ts"]) if processed_rows else None,
    }


def write_outputs(report: dict[str, Any]) -> dict[str, str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = LOG_DIR / f"22012_recent8h_pg_pspace_audit_{stamp}.json"
    csv_path = LOG_DIR / f"22012_recent8h_pg_tag_coverage_{stamp}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "variable_name",
            "tag_long_name",
            "expected_minutes",
            "row_count",
            "missing_rows",
            "null_rows",
            "effective_missing_rows",
            "min_ts",
            "max_ts",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["postgres"]["tag_coverage"]:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return {"json": str(json_path), "csv": str(csv_path)}


def main() -> int:
    hours = float(os.getenv("AUDIT_HOURS", "8"))
    conn = connect(SYNC_ROOT / "config" / "sync_config.json")
    start, end, registry = db_window_and_registry(conn, hours)
    postgres_report = query_db_coverage(conn, start, end, registry)
    pspace_report = pspace_raw_and_processed(start, end)
    report = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "window_basis": "PostgreSQL max(ts) ending window",
        "window_start": text_time(start),
        "window_end": text_time(end),
        "postgres": postgres_report,
        "pspace_243_top_d": pspace_report,
    }
    outputs = write_outputs(report)
    report["outputs"] = outputs
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
