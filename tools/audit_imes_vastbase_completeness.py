# -*- coding: utf-8 -*-
"""Read-only daily completeness audit for the verified IMES Vastbase objects.

The script never exports business rows.  It aggregates only counts and date
bounds for objects that ``export_vastbase_local.py`` has proven selectable.
Requirement: REQ-IMES-22012-RELAY-MCP-20260716
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Sequence

import psycopg

from export_vastbase_local import (
    DbObject,
    connection_info,
    discover_objects,
    parse_iso_date,
    qualified_sql,
    quote_identifier,
)


DEFAULT_OBJECTS = {
    "public.batch_input",
    "public.inner_batch_insp_bb",
    "public.slag_inspection",
    "public.t_ipes_cond",
    "public.t_ipes_out_put",
    "public.t_qpes_inner_batch",
}


def object_columns(item: DbObject) -> dict[str, str]:
    return {column.lower(): column for column in item.columns}


def two_furnace_condition(item: DbObject) -> str | None:
    """Return a conservative SQL condition identifying 2# rows, if possible."""

    columns = object_columns(item)
    checks: list[str] = []
    if "prodcentercode" in columns:
        value = quote_identifier(columns["prodcentercode"])
        checks.append(f"TRIM(CAST({value} AS TEXT)) IN ('2', '2D012')")
    for name in ("meltno", "heatno"):
        if name in columns:
            value = quote_identifier(columns[name])
            # psycopg treats a literal percent as a placeholder marker, even
            # when it appears inside a SQL string literal.
            checks.append(f"CAST({value} AS TEXT) LIKE '2#%%'")
    return " OR ".join(checks) if checks else None


def date_window(item: DbObject, start_date: str, end_date: str) -> tuple[str, tuple[str, str]]:
    """Return an inclusive business-day filter without Vastbase DATE coercion.

    Vastbase's DATE cast retains time-of-day for some timestamp-compatible
    columns.  A half-open raw-column interval preserves index eligibility and
    avoids incorrectly grouping each timestamp as a different day.
    """

    if not item.date_column:
        raise ValueError(f"{item.qualified_name} has no recognized date column")
    end_exclusive = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
    column = quote_identifier(item.date_column)
    return f"{column} >= %s AND {column} < %s", (start_date, end_exclusive)


def business_day_expr(item: DbObject) -> str:
    """Normalize date/timestamp-like values to ISO day text for grouping."""

    if not item.date_column:
        raise ValueError(f"{item.qualified_name} has no recognized date column")
    return f"SUBSTR(CAST({quote_identifier(item.date_column)} AS TEXT), 1, 10)"


def build_summary_query(item: DbObject, start_date: str, end_date: str) -> tuple[str, tuple[Any, ...]]:
    if not item.date_column:
        raise ValueError(f"{item.qualified_name} has no recognized date column")
    window_sql, window_params = date_window(item, start_date, end_date)
    raw_date = quote_identifier(item.date_column)
    two_condition = two_furnace_condition(item)
    coverage = (
        f", COALESCE(SUM(CASE WHEN {two_condition} THEN 1 ELSE 0 END), 0) AS two_furnace_rows"
        if two_condition
        else ", NULL::bigint AS two_furnace_rows"
    )
    sql = (
        f"SELECT MIN({raw_date}) AS oldest_date, MAX({raw_date}) AS newest_date, COUNT(*) AS total_rows"
        f"{coverage} FROM {qualified_sql(item.schema, item.name)} "
        f"WHERE {window_sql}"
    )
    return sql, window_params


def build_daily_query(item: DbObject, start_date: str, end_date: str) -> tuple[str, tuple[Any, ...]]:
    if not item.date_column:
        raise ValueError(f"{item.qualified_name} has no recognized date column")
    window_sql, window_params = date_window(item, start_date, end_date)
    date_expr = business_day_expr(item)
    two_condition = two_furnace_condition(item)
    coverage = (
        f"COALESCE(SUM(CASE WHEN {two_condition} THEN 1 ELSE 0 END), 0)"
        if two_condition
        else "NULL::bigint"
    )
    sql = (
        f"SELECT {date_expr} AS business_date, COUNT(*) AS total_rows, {coverage} AS two_furnace_rows "
        f"FROM {qualified_sql(item.schema, item.name)} "
        f"WHERE {window_sql} "
        f"GROUP BY {date_expr} ORDER BY {date_expr}"
    )
    return sql, window_params


def audit_object(cur: Any, item: DbObject, start_date: str, end_date: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary_sql, summary_params = build_summary_query(item, start_date, end_date)
    cur.execute(summary_sql, summary_params)
    oldest, newest, total, two_rows = cur.fetchone()
    daily_sql, daily_params = build_daily_query(item, start_date, end_date)
    cur.execute(daily_sql, daily_params)
    daily = [
        {
            "object": item.qualified_name,
            "date": str(day),
            "total_rows": int(rows),
            "two_furnace_rows": None if two is None else int(two),
            "two_furnace_coverage_pct": None if two is None or not rows else round(int(two) * 100 / int(rows), 2),
        }
        for day, rows, two in cur.fetchall()
    ]
    return (
        {
            "object": item.qualified_name,
            "category": item.category,
            "date_column": item.date_column,
            "period_oldest_date": None if oldest is None else str(oldest),
            "period_newest_date": None if newest is None else str(newest),
            "period_total_rows": int(total),
            "period_two_furnace_rows": None if two_rows is None else int(two_rows),
            "period_two_furnace_coverage_pct": None
            if two_rows is None or not total
            else round(int(two_rows) * 100 / int(total), 2),
            "daily_days": len(daily),
        },
        daily,
    )


def write_report(output_dir: Path, report: dict[str, Any], daily: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "imes_vastbase_completeness_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "imes_vastbase_daily_counts.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["object", "date", "total_rows", "two_furnace_rows", "two_furnace_coverage_pct"])
        writer.writeheader()
        writer.writerows(daily)
    lines = [
        "# IMES Vastbase 完整性审计", "", f"审计窗口：`{report['start_date']}` 至 `{report['end_date']}`。", "",
        "| 对象 | 日期字段 | 最早/最新（窗口内） | 总行数 | 2#行数 | 2#覆盖率 | 有数据天数 |", "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in report["objects"]:
        date_span = f"{item['period_oldest_date'] or '-'} / {item['period_newest_date'] or '-'}"
        two_rows = "-" if item["period_two_furnace_rows"] is None else str(item["period_two_furnace_rows"])
        coverage = "-" if item["period_two_furnace_coverage_pct"] is None else f"{item['period_two_furnace_coverage_pct']}%"
        lines.append(f"| `{item['object']}` | `{item['date_column']}` | {date_span} | {item['period_total_rows']} | {two_rows} | {coverage} | {item['daily_days']} |")
    lines.extend(["", "说明：2# 覆盖率按 `prodcentercode IN ('2','2D012')` 或炉次号以 `2#` 开头的保守规则统计；不代表生产完整率。日期范围以本次审计窗口为准，不声称是全库保留期。"])
    (output_dir / "imes_vastbase_completeness_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只读审计 IMES Vastbase 每日行数与 2# 覆盖率。")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15433)
    parser.add_argument("--database", default="vastbase")
    parser.add_argument("--connect-timeout", type=int, default=12)
    parser.add_argument("--statement-timeout-ms", type=int, default=60000)
    parser.add_argument("--start-date", type=parse_iso_date, required=True)
    parser.add_argument("--end-date", type=parse_iso_date, default=date.today().isoformat())
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if date.fromisoformat(args.start_date) > date.fromisoformat(args.end_date):
        raise SystemExit("--start-date must not be after --end-date")
    info = connection_info(args)
    with psycopg.connect(**info) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            objects = {item.qualified_name: item for item in discover_objects(cur)}
            verified = [objects[name] for name in sorted(DEFAULT_OBJECTS) if name in objects and objects[name].selectable]
            summaries: list[dict[str, Any]] = []
            daily: list[dict[str, Any]] = []
            failures: list[dict[str, str]] = []
            for item in verified:
                try:
                    summary, rows = audit_object(cur, item, args.start_date, args.end_date)
                    summaries.append(summary)
                    daily.extend(rows)
                    print(f"{item.qualified_name}: {summary['period_total_rows']} rows, {summary['daily_days']} days")
                except psycopg.Error as exc:
                    conn.rollback()
                    cur.execute("SET TRANSACTION READ ONLY")
                    failures.append({"object": item.qualified_name, "error": f"{type(exc).__name__}: {exc}"})
            report = {"start_date": args.start_date, "end_date": args.end_date, "objects": summaries, "failures": failures}
            write_report(args.output_dir, report, daily)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
