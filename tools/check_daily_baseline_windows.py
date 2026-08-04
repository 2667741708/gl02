#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check that daily baseline rows use the expected rolling 30-day window."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate bf_sensor.daily_baselines rolling windows.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15432)
    parser.add_argument("--database", default="bf_trend")
    parser.add_argument("--user", default="gl02_sync")
    parser.add_argument("--password", default="gl02_local_sync")
    parser.add_argument("--start-day", default="2026-05-01")
    parser.add_argument("--end-day", default="2026-05-14")
    parser.add_argument("--baseline-days", type=int, default=30)
    parser.add_argument("--out-prefix", default="daily_baseline_window_check")
    args = parser.parse_args()

    params: dict[str, Any] = {
        "host": args.host,
        "port": args.port,
        "dbname": args.database,
        "user": args.user,
        "password": args.password,
        "connect_timeout": 8,
    }
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        overview = conn.execute(
            """
            SELECT min(baseline_day) AS min_day,
                   max(baseline_day) AS max_day,
                   count(DISTINCT baseline_day) AS days,
                   count(*) AS rows
            FROM bf_sensor.daily_baselines
            WHERE baseline_days = %s
            """,
            (args.baseline_days,),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT baseline_day,
                   count(*) AS variables,
                   min(baseline_window_start) AS window_start_min,
                   max(baseline_window_start) AS window_start_max,
                   min(baseline_window_end) AS window_end_min,
                   max(baseline_window_end) AS window_end_max,
                   min(baseline_days) AS min_days,
                   max(baseline_days) AS max_days,
                   round(avg(coverage_ratio)::numeric, 4) AS avg_coverage,
                   min(updated_at) AS first_updated_at,
                   max(updated_at) AS last_updated_at,
                   bool_and(baseline_window_start = baseline_day::timestamp - (%s::text || ' days')::interval) AS start_ok,
                   bool_and(baseline_window_end = baseline_day::timestamp - interval '1 minute') AS end_ok,
                   bool_and(baseline_days = %s) AS days_ok
            FROM bf_sensor.daily_baselines
            WHERE baseline_day >= %s::date
              AND baseline_day <= %s::date
            GROUP BY baseline_day
            ORDER BY baseline_day
            """,
            (args.baseline_days, args.baseline_days, args.start_day, args.end_day),
        ).fetchall()

    records = [dict(row) for row in rows]
    bad = [
        row
        for row in records
        if not row.get("start_ok") or not row.get("end_ok") or not row.get("days_ok")
    ]
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": f"{args.host}:{args.port}/{args.database}",
        "baseline_days": args.baseline_days,
        "start_day": args.start_day,
        "end_day": args.end_day,
        "overview": dict(overview or {}),
        "days_checked": len(records),
        "bad_days": len(bad),
        "ok": not bad,
        "rows": records,
    }

    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    json_path = logs / f"{args.out_prefix}.json"
    md_path = logs / f"{args.out_prefix}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2), encoding="utf-8")

    lines = [
        "# daily_baselines 滚动窗口检查",
        "",
        f"- 生成时间：`{result['generated_at']}`",
        f"- 数据库：`{result['database']}`",
        f"- baseline_days：`{args.baseline_days}`",
        f"- 检查范围：`{args.start_day}` 到 `{args.end_day}`",
        f"- 检查天数：`{result['days_checked']}`",
        f"- 异常天数：`{result['bad_days']}`",
        "",
        "| 基线日 | 变量数 | 窗口开始 | 窗口结束 | 30天口径 | 开始正确 | 结束正确 | 平均覆盖率 | 最后更新 |",
        "|---|---:|---|---|---|---|---|---:|---|",
    ]
    for row in records:
        lines.append(
            "| {baseline_day} | {variables} | {window_start_min} | {window_end_min} | {days_ok} | {start_ok} | {end_ok} | {avg_coverage} | {last_updated_at} |".format(
                **row
            )
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"ok": result["ok"], "bad_days": len(bad), "json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
