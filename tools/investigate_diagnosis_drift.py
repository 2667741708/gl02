#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read-only audit for recent diagnosis distribution drift.

The script intentionally uses Python-only PostgreSQL access so it can be used
for local and server-side checks without hand-written shell/SQL pipelines.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"

LABELS = ["normal", "cold", "hot", "edge", "channel", "column", "data_quality_low", "sync_pending"]
KEY_VARIABLES = [
    "P_blast",
    "Q_blast",
    "P_top",
    "DP_total",
    "PI",
    "GasUtil",
    "L",
    "T_blast",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "PCI_rate",
]


def pg_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "host": args.host or os.environ.get("GL02_PGHOST", "127.0.0.1"),
        "port": int(args.port or os.environ.get("GL02_PGPORT", "15432")),
        "dbname": args.database or os.environ.get("GL02_PGDATABASE", "bf_trend"),
        "user": args.user or os.environ.get("GL02_PGUSER", "gl02_sync"),
        "password": args.password or os.environ.get("GL02_PGPASSWORD", "gl02_local_sync"),
        "connect_timeout": int(args.connect_timeout),
    }


def scrub_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: ("***" if k == "password" else v) for k, v in params.items()}


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat(sep=" ")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__float__"):
        try:
            return float(value)
        except Exception:
            pass
    return str(value)


def fetch_all(conn: psycopg.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def fetch_one(conn: psycopg.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def label_columns_sql(prefix: str = "") -> str:
    cols = []
    for label in LABELS:
        cols.append(f"count(*) FILTER (WHERE main_label = '{label}') AS {prefix}{label}")
    return ",\n                   ".join(cols)


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    params = pg_params(args)
    since_expr = f"now() - interval '{int(args.days)} days'"
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        overview = fetch_one(
            conn,
            """
            SELECT
                (SELECT min(ts) FROM bf_sensor.one_minute_values) AS sensor_min_ts,
                (SELECT max(ts) FROM bf_sensor.one_minute_values) AS sensor_max_ts,
                (SELECT count(*) FROM bf_sensor.one_minute_values) AS sensor_rows,
                (SELECT count(distinct tag_long_name) FROM bf_sensor.one_minute_values) AS sensor_tags,
                (SELECT min(baseline_day) FROM bf_sensor.daily_baselines WHERE baseline_days=30) AS baseline_min_day,
                (SELECT max(baseline_day) FROM bf_sensor.daily_baselines WHERE baseline_days=30) AS baseline_max_day,
                (SELECT count(distinct baseline_day) FROM bf_sensor.daily_baselines WHERE baseline_days=30) AS baseline_days,
                (SELECT min(diagnosis_ts) FROM bf_sensor.diagnosis_snapshots) AS diagnosis_min_ts,
                (SELECT max(diagnosis_ts) FROM bf_sensor.diagnosis_snapshots) AS diagnosis_max_ts,
                (SELECT count(*) FROM bf_sensor.diagnosis_snapshots) AS diagnosis_rows
            """
        )

        all_distribution = fetch_all(
            conn,
            f"""
            SELECT diagnosis_ts::date AS day,
                   count(*) AS all_rows,
                   count(DISTINCT diagnosis_ts) AS distinct_points,
                   count(*) - count(DISTINCT diagnosis_ts) AS duplicate_extra_rows,
                   {label_columns_sql('all_')},
                   array_agg(DISTINCT COALESCE(source->>'rule_profile','')) AS rule_profiles,
                   array_agg(DISTINCT COALESCE(source->>'rule_profile_variables','')) AS rule_profile_variables,
                   min(created_at) AS first_created_at,
                   max(updated_at) AS last_updated_at
            FROM bf_sensor.diagnosis_snapshots
            WHERE diagnosis_ts >= {since_expr}
            GROUP BY diagnosis_ts::date
            ORDER BY day
            """
        )

        latest_distribution = fetch_all(
            conn,
            f"""
            WITH latest AS (
                SELECT DISTINCT ON (diagnosis_ts) *
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= {since_expr}
                ORDER BY diagnosis_ts, updated_at DESC, id DESC
            )
            SELECT diagnosis_ts::date AS day,
                   count(*) AS points,
                   {label_columns_sql()},
                   round(avg(COALESCE((data_coverage->>'coverage_ratio')::numeric, 0)), 4) AS avg_coverage,
                   min(COALESCE((data_coverage->>'coverage_ratio')::numeric, 0)) AS min_coverage,
                   count(*) FILTER (WHERE raw_scores = '{{}}'::jsonb) AS empty_raw_scores,
                   count(*) FILTER (WHERE COALESCE(feature_snapshot, '{{}}'::jsonb) <> '{{}}'::jsonb) AS nonempty_feature_snapshots,
                   array_agg(DISTINCT COALESCE(source->>'rule_profile','')) AS rule_profiles,
                   array_agg(DISTINCT COALESCE(source->>'rule_profile_variables','')) AS rule_profile_variables,
                   min(diagnosis_window_start) AS min_diag_window_start,
                   max(diagnosis_window_end) AS max_diag_window_end,
                   min(baseline_window_start) AS min_snapshot_baseline_start,
                   max(baseline_window_end) AS max_snapshot_baseline_end,
                   min(created_at) AS first_created_at,
                   max(updated_at) AS last_updated_at
            FROM latest
            GROUP BY diagnosis_ts::date
            ORDER BY day
            """
        )

        rule_profile_timeline = fetch_all(
            conn,
            f"""
            SELECT diagnosis_ts::date AS day,
                   COALESCE(source->>'rule_profile','') AS rule_profile,
                   COALESCE(source->>'rule_profile_variables','') AS rule_profile_variables,
                   count(*) AS rows,
                   count(DISTINCT diagnosis_ts) AS distinct_points,
                   min(created_at) AS first_created_at,
                   max(updated_at) AS last_updated_at
            FROM bf_sensor.diagnosis_snapshots
            WHERE diagnosis_ts >= {since_expr}
            GROUP BY diagnosis_ts::date, COALESCE(source->>'rule_profile',''), COALESCE(source->>'rule_profile_variables','')
            ORDER BY day, rule_profile, rule_profile_variables
            """
        )

        duplicate_points = fetch_all(
            conn,
            f"""
            SELECT diagnosis_ts,
                   count(*) AS rows,
                   array_agg(DISTINCT COALESCE(source->>'rule_profile','')) AS rule_profiles,
                   array_agg(DISTINCT COALESCE(source->>'rule_profile_variables','')) AS rule_profile_variables,
                   array_agg(DISTINCT main_label) AS labels,
                   min(created_at) AS first_created_at,
                   max(updated_at) AS last_updated_at
            FROM bf_sensor.diagnosis_snapshots
            WHERE diagnosis_ts >= {since_expr}
            GROUP BY diagnosis_ts
            HAVING count(*) > 1
            ORDER BY diagnosis_ts DESC
            LIMIT 200
            """
        )

        baseline_by_day = fetch_all(
            conn,
            f"""
            SELECT baseline_day,
                   count(*) AS variables,
                   min(baseline_window_start) AS window_start_min,
                   max(baseline_window_start) AS window_start_max,
                   min(baseline_window_end) AS window_end_min,
                   max(baseline_window_end) AS window_end_max,
                   min(sample_count) AS min_sample_count,
                   max(sample_count) AS max_sample_count,
                   round(avg(coverage_ratio)::numeric, 4) AS avg_coverage,
                   min(coverage_ratio) AS min_coverage,
                   count(*) FILTER (WHERE coverage_ratio < 0.75) AS low_coverage_variables,
                   min(created_at) AS first_created_at,
                   max(updated_at) AS last_updated_at
            FROM bf_sensor.daily_baselines
            WHERE baseline_days = 30
              AND baseline_day >= ({since_expr})::date
            GROUP BY baseline_day
            ORDER BY baseline_day
            """
        )

        baseline_key_variables = fetch_all(
            conn,
            f"""
            SELECT baseline_day, variable_name, median_ref, iqr_ref, sample_count, coverage_ratio, updated_at
            FROM bf_sensor.daily_baselines
            WHERE baseline_days = 30
              AND baseline_day >= ({since_expr})::date
              AND variable_name = ANY(%s)
            ORDER BY baseline_day, variable_name
            """,
            (KEY_VARIABLES,),
        )

        daily_key_variable_stats = fetch_all(
            conn,
            f"""
            SELECT v.ts::date AS day,
                   r.variable_name,
                   count(*) AS rows,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY v.value) AS median_value,
                   avg(v.value) AS avg_value,
                   min(v.value) AS min_value,
                   max(v.value) AS max_value,
                   count(*) FILTER (WHERE v.value = 0) AS zero_rows
            FROM bf_sensor.one_minute_values v
            JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
            WHERE v.ts >= {since_expr}
              AND r.variable_name = ANY(%s)
            GROUP BY v.ts::date, r.variable_name
            ORDER BY day, variable_name
            """,
            (KEY_VARIABLES,),
        )

        coverage_recent = fetch_all(
            conn,
            f"""
            SELECT checked_at::date AS day,
                   window_kind,
                   count(*) AS checks,
                   round(avg(coverage_ratio)::numeric, 4) AS avg_coverage,
                   min(coverage_ratio) AS min_coverage,
                   array_agg(DISTINCT status) AS statuses,
                   max(checked_at) AS last_checked_at
            FROM bf_sensor.data_quality_status
            WHERE checked_at >= {since_expr}
            GROUP BY checked_at::date, window_kind
            ORDER BY day, window_kind
            """
        )

        zero_stats = fetch_all(
            conn,
            f"""
            SELECT v.ts::date AS day,
                   r.variable_name,
                   count(*) FILTER (WHERE v.value = 0) AS zero_rows,
                   count(*) AS rows,
                   count(*) FILTER (WHERE v.value = 0 AND z.verification_status = 'verified_zero') AS verified_zero_rows,
                   count(*) FILTER (WHERE v.value = 0 AND z.verification_status IS NULL) AS unaudited_zero_rows,
                   count(*) FILTER (WHERE v.value = 0 AND z.verification_status IS NOT NULL AND z.verification_status <> 'verified_zero') AS rejected_zero_rows
            FROM bf_sensor.one_minute_values v
            JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
            LEFT JOIN bf_sensor.zero_value_audits z
              ON z.tag_long_name = v.tag_long_name
             AND z.ts = v.ts
             AND z.pspace_aggregate = v.aggregate
            WHERE v.ts >= {since_expr}
              AND r.variable_name = ANY(%s)
            GROUP BY v.ts::date, r.variable_name
            HAVING count(*) FILTER (WHERE v.value = 0) > 0
            ORDER BY day, variable_name
            """,
            (KEY_VARIABLES,),
        )

        recent_runs = fetch_all(
            conn,
            """
            SELECT started_at, finished_at, task_name, status, window_start, window_end,
                   rows_read, rows_written, message, details
            FROM bf_sensor.automation_runs
            ORDER BY started_at DESC
            LIMIT 80
            """
        )

        latest_examples = fetch_all(
            conn,
            """
            SELECT diagnosis_ts, main_label, main_score, secondary_label, secondary_score,
                   source->>'rule_profile' AS rule_profile,
                   source->>'rule_profile_variables' AS rule_profile_variables,
                   data_coverage->>'coverage_ratio' AS coverage_ratio,
                   baseline_days, window_minutes, baseline_window_start, baseline_window_end,
                   raw_scores, evidence, updated_at
            FROM (
                SELECT DISTINCT ON (diagnosis_ts) *
                FROM bf_sensor.diagnosis_snapshots
                ORDER BY diagnosis_ts DESC, updated_at DESC, id DESC
            ) latest
            ORDER BY diagnosis_ts DESC
            LIMIT 24
            """
        )

    report = {
        "generated_at": datetime.now(),
        "database": scrub_params(params),
        "days": int(args.days),
        "overview": overview,
        "all_distribution": all_distribution,
        "latest_distribution": latest_distribution,
        "rule_profile_timeline": rule_profile_timeline,
        "duplicate_points": duplicate_points,
        "baseline_by_day": baseline_by_day,
        "baseline_key_variables": baseline_key_variables,
        "daily_key_variable_stats": daily_key_variable_stats,
        "coverage_recent": coverage_recent,
        "zero_stats": zero_stats,
        "recent_runs": recent_runs,
        "latest_examples": latest_examples,
        "findings": summarize_findings(all_distribution, latest_distribution, rule_profile_timeline, duplicate_points, baseline_by_day),
    }
    return report


def summarize_findings(
    all_distribution: list[dict[str, Any]],
    latest_distribution: list[dict[str, Any]],
    rule_profile_timeline: list[dict[str, Any]],
    duplicate_points: list[dict[str, Any]],
    baseline_by_day: list[dict[str, Any]],
) -> list[str]:
    findings: list[str] = []
    if duplicate_points:
        extra = sum(int(row.get("rows") or 0) - 1 for row in duplicate_points)
        findings.append(f"发现同一 diagnosis_ts 存在多版本记录，样例 {len(duplicate_points)} 个，至少多出 {extra} 行；仪表盘若不去重会混入旧版本。")
    else:
        findings.append("未发现最近窗口内 diagnosis_ts 多版本重复记录。")

    profiles_by_day: dict[str, set[str]] = defaultdict(set)
    for row in rule_profile_timeline:
        profiles_by_day[str(row.get("day"))].add(str(row.get("rule_profile") or ""))
    mixed = {day: sorted(p for p in profiles if p) for day, profiles in profiles_by_day.items() if len({p for p in profiles if p}) > 1}
    profiles = sorted({str(row.get("rule_profile") or "") for row in rule_profile_timeline if row.get("rule_profile")})
    if mixed:
        findings.append(f"发现同一天混用多个 rule_profile：{mixed}")
    elif len(profiles) > 1:
        findings.append(f"最近窗口跨日期存在 rule_profile 切换：{profiles}")
    elif profiles:
        findings.append(f"最近窗口规则 profile 单一：{profiles[0]}")
    else:
        findings.append("诊断 source 中没有记录 rule_profile，无法从库内确认规则版本。")

    weak_baselines = [
        row for row in baseline_by_day
        if int(row.get("variables") or 0) < 100 or float(row.get("min_coverage") or 0) < 0.75
    ]
    if weak_baselines:
        days = [str(row.get("baseline_day")) for row in weak_baselines[:10]]
        findings.append(f"存在变量数不足或覆盖率低于 0.75 的 30 天基线日：{days}")
    elif baseline_by_day:
        findings.append("最近窗口 daily_baselines 每日均有较完整记录，未见明显缺日/低覆盖。")
    else:
        findings.append("最近窗口没有查到 30 天 daily_baselines。")

    drift_days: list[str] = []
    for row in latest_distribution:
        points = int(row.get("points") or 0)
        if not points:
            continue
        abnormal = points - int(row.get("normal") or 0)
        if abnormal / points >= 0.30:
            drift_days.append(f"{row.get('day')}({abnormal}/{points})")
    if drift_days:
        findings.append("按最新版本去重后，异常占比超过 30% 的日期：" + ", ".join(drift_days[:12]))
    else:
        findings.append("按最新版本去重后，最近窗口未出现大面积异常占比跳变。")

    raw_extra_days = [
        f"{row.get('day')}(+{row.get('duplicate_extra_rows')})"
        for row in all_distribution
        if int(row.get("duplicate_extra_rows") or 0) > 0
    ]
    if raw_extra_days:
        findings.append("仪表盘原始计数可能受重复版本影响的日期：" + ", ".join(raw_extra_days[:12]))
    return findings


def write_markdown(report: dict[str, Any], path: Path) -> None:
    latest_distribution = report["latest_distribution"]
    all_distribution = report["all_distribution"]
    baseline_by_day = report["baseline_by_day"]
    lines: list[str] = []
    lines.append("# 炉况分布漂移只读审查报告")
    lines.append("")
    lines.append(f"- 生成时间：`{json_default(report['generated_at'])}`")
    lines.append(f"- 数据库：`{report['database']['host']}:{report['database']['port']}/{report['database']['dbname']}`")
    lines.append(f"- 审查天数：`{report['days']}`")
    lines.append("")
    lines.append("## 初步发现")
    for item in report["findings"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 最新版本去重后的每日分布")
    lines.append("")
    lines.append("| 日期 | 点数 | 正常 | 炉凉 | 炉热 | 边缘 | 管道 | 悬料 | 数据质量低 | 平均覆盖率 | 规则 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in latest_distribution:
        lines.append(
            "| {day} | {points} | {normal} | {cold} | {hot} | {edge} | {channel} | {column} | {data_quality_low} | {avg_coverage} | {profiles} |".format(
                day=row.get("day"),
                points=row.get("points"),
                normal=row.get("normal"),
                cold=row.get("cold"),
                hot=row.get("hot"),
                edge=row.get("edge"),
                channel=row.get("channel"),
                column=row.get("column"),
                data_quality_low=row.get("data_quality_low"),
                avg_coverage=row.get("avg_coverage"),
                profiles=",".join(str(x) for x in row.get("rule_profiles") or []),
            )
        )
    lines.append("")
    lines.append("## 仪表盘原始计数重复性检查")
    lines.append("")
    lines.append("| 日期 | 原始行数 | 诊断点数 | 多余版本行 | 规则 |")
    lines.append("|---|---:|---:|---:|---|")
    for row in all_distribution:
        lines.append(
            f"| {row.get('day')} | {row.get('all_rows')} | {row.get('distinct_points')} | {row.get('duplicate_extra_rows')} | {','.join(str(x) for x in row.get('rule_profiles') or [])} |"
        )
    lines.append("")
    lines.append("## 30天基线每日完整性")
    lines.append("")
    lines.append("| 基线日 | 变量数 | 窗口开始 | 窗口结束 | 最低覆盖率 | 平均覆盖率 | 低覆盖变量数 | 最后更新 |")
    lines.append("|---|---:|---|---|---:|---:|---:|---|")
    for row in baseline_by_day:
        lines.append(
            f"| {row.get('baseline_day')} | {row.get('variables')} | {row.get('window_start_min')} | {row.get('window_end_max')} | {row.get('min_coverage')} | {row.get('avg_coverage')} | {row.get('low_coverage_variables')} | {row.get('last_updated_at')} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only diagnosis drift audit.")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", default="")
    parser.add_argument("--database", default="")
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--out-prefix", default="")
    args = parser.parse_args()

    report = run_audit(args)
    LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = args.out_prefix or f"diagnosis_drift_audit_{stamp}"
    json_path = LOG_DIR / f"{prefix}.json"
    md_path = LOG_DIR / f"{prefix}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    write_markdown(report, md_path)
    print(json.dumps({
        "ok": True,
        "json": str(json_path),
        "markdown": str(md_path),
        "findings": report["findings"],
        "overview": report["overview"],
    }, ensure_ascii=False, indent=2, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
