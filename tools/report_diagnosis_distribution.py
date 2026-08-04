#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Report diagnosis label distribution from PostgreSQL snapshots.

The report intentionally uses the same deduplication rule as the 8890 dashboard:
for each diagnosis_ts, keep the latest row by updated_at/id.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
LABELS = [
    "normal",
    "cold",
    "hot",
    "edge",
    "channel",
    "column",
    "data_quality_low",
    "sync_pending",
]
LABEL_CN = {
    "normal": "正常",
    "cold": "炉凉",
    "hot": "炉热",
    "edge": "边缘煤气流发展",
    "channel": "管道行程",
    "column": "中心过吹/边缘不足",
    "data_quality_low": "数据质量低",
    "sync_pending": "同步等待",
}


def pg_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "host": args.host,
        "port": args.port,
        "dbname": args.database,
        "user": args.user,
        "password": args.password,
        "connect_timeout": 8,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize bf_sensor.diagnosis_snapshots distribution.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15432)
    parser.add_argument("--database", default="bf_trend")
    parser.add_argument("--user", default="gl02_sync")
    parser.add_argument("--password", default="gl02_local_sync")
    parser.add_argument("--start", default="2026-04-14 00:00:00")
    parser.add_argument("--end", default="2026-05-15 00:00:00", help="Exclusive end timestamp.")
    parser.add_argument("--out-prefix", default="monthly_diagnosis_distribution_20260414_20260514")
    args = parser.parse_args()

    params = pg_params(args)
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        overall = conn.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (diagnosis_ts)
                       diagnosis_ts, main_label
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= %s AND diagnosis_ts < %s
                ORDER BY diagnosis_ts, updated_at DESC, id DESC
            )
            SELECT main_label, count(*) AS n,
                   round(count(*) * 100.0 / sum(count(*)) over (), 2) AS pct
            FROM latest
            GROUP BY main_label
            ORDER BY n DESC, main_label
            """,
            (args.start, args.end),
        ).fetchall()

        daily = conn.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (diagnosis_ts)
                       diagnosis_ts, main_label, data_coverage,
                       source->>'rule_profile' AS rule_profile,
                       updated_at
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= %s AND diagnosis_ts < %s
                ORDER BY diagnosis_ts, updated_at DESC, id DESC
            )
            SELECT diagnosis_ts::date AS day,
                   count(*) AS points,
                   count(*) FILTER (WHERE main_label='normal') AS normal,
                   count(*) FILTER (WHERE main_label='cold') AS cold,
                   count(*) FILTER (WHERE main_label='hot') AS hot,
                   count(*) FILTER (WHERE main_label='edge') AS edge,
                   count(*) FILTER (WHERE main_label='channel') AS channel,
                   count(*) FILTER (WHERE main_label='column') AS column,
                   count(*) FILTER (WHERE main_label='data_quality_low') AS data_quality_low,
                   count(*) FILTER (WHERE main_label='sync_pending') AS sync_pending,
                   round(avg(COALESCE((data_coverage->>'coverage_ratio')::numeric, 0)), 4) AS avg_coverage,
                   string_agg(DISTINCT coalesce(rule_profile,''), ',' ORDER BY coalesce(rule_profile,'')) AS rule_profiles,
                   min(updated_at) AS first_updated_at,
                   max(updated_at) AS last_updated_at
            FROM latest
            GROUP BY diagnosis_ts::date
            ORDER BY day
            """,
            (args.start, args.end),
        ).fetchall()

        profile_timeline = conn.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (diagnosis_ts)
                       diagnosis_ts,
                       source->>'rule_profile' AS rule_profile,
                       source->>'rule_profile_variables' AS rule_profile_variables
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= %s AND diagnosis_ts < %s
                ORDER BY diagnosis_ts, updated_at DESC, id DESC
            )
            SELECT diagnosis_ts::date AS day,
                   coalesce(rule_profile,'') AS rule_profile,
                   coalesce(rule_profile_variables,'') AS rule_profile_variables,
                   count(*) AS rows
            FROM latest
            GROUP BY diagnosis_ts::date, coalesce(rule_profile,''), coalesce(rule_profile_variables,'')
            ORDER BY day, rule_profile
            """,
            (args.start, args.end),
        ).fetchall()

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": f"{args.host}:{args.port}/{args.database}",
        "window_start": args.start,
        "window_end_exclusive": args.end,
        "overall": [dict(row) for row in overall],
        "daily": [dict(row) for row in daily],
        "profile_timeline": [dict(row) for row in profile_timeline],
    }

    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    json_path = logs / f"{args.out_prefix}.json"
    md_path = logs / f"{args.out_prefix}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2), encoding="utf-8")

    lines = [
        "# 炉况分布汇总",
        "",
        f"- 生成时间：`{result['generated_at']}`",
        f"- 数据库：`{result['database']}`",
        f"- 窗口：`{args.start}` 到 `{args.end}`（不含结束）",
        "- 口径：`diagnosis_snapshots` 按 `diagnosis_ts` 去重，只保留最新版本。",
        "",
        "## 总分布",
        "",
        "| 炉况 | 点数 | 占比 |",
        "|---|---:|---:|",
    ]
    for row in overall:
        lines.append(f"| {LABEL_CN.get(row['main_label'], row['main_label'])} | {row['n']} | {row['pct']}% |")

    lines.extend(
        [
            "",
            "## 每日分布",
            "",
            "| 日期 | 点数 | 正常 | 炉凉 | 炉热 | 边缘煤气流发展 | 管道行程 | 中心过吹/边缘不足 | 数据质量低 | 平均覆盖率 | 规则记录 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in daily:
        lines.append(
            "| {day} | {points} | {normal} | {cold} | {hot} | {edge} | {channel} | {column} | "
            "{data_quality_low} | {avg_coverage} | {rule_profiles} |".format(
                **{**row, "rule_profiles": row["rule_profiles"] or "未记录"}
            )
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "json": str(json_path),
                "md": str(md_path),
                "days": len(daily),
                "overall": result["overall"],
            },
            ensure_ascii=False,
            default=str,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
