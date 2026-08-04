#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Replay current full115 diagnosis rules and compare with stored snapshots.

This is a read-only audit tool.  It does not write bf_sensor tables.  For every
stored diagnosis_ts in the selected window it:
1. keeps the latest stored snapshot by updated_at/id;
2. runs AutoDiagnosisScheduler.diagnose_point(..., dry_run=True) with
   GL02_RULE_PROFILE=full115;
3. writes full per-point results plus mismatch-only reports.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row
import yaml


ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "自动诊断服务"
LOG_DIR = ROOT / "logs"

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


def json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("T", " ")).replace(second=0, microsecond=0)


def pg_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "host": args.host,
        "port": args.port,
        "dbname": args.database,
        "user": args.user,
        "password": args.password,
        "connect_timeout": 8,
    }


def set_env(args: argparse.Namespace) -> None:
    os.environ["GL02_PGHOST"] = args.host
    os.environ["GL02_PGPORT"] = str(args.port)
    os.environ["GL02_PGDATABASE"] = args.database
    os.environ["GL02_PGUSER"] = args.user
    os.environ["GL02_PGPASSWORD"] = args.password
    os.environ["GL02_RULE_PROFILE"] = "full115"


def fetch_latest_snapshots(args: argparse.Namespace) -> list[dict[str, Any]]:
    params = pg_params(args)
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM (
                SELECT DISTINCT ON (diagnosis_ts)
                       id, diagnosis_ts, main_label, main_score, main_confidence,
                       secondary_label, secondary_score, secondary_confidence,
                       data_coverage, raw_scores, evidence, source, updated_at, created_at
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= %s AND diagnosis_ts < %s
                ORDER BY diagnosis_ts, updated_at DESC, id DESC
            ) latest
            ORDER BY diagnosis_ts ASC
            """,
            (args.start, args.end),
        ).fetchall()
    records = [dict(row) for row in rows]
    if args.limit:
        records = records[: args.limit]
    return records


def score_for(label: str | None, scores: Any) -> float | None:
    if not label or not isinstance(scores, dict):
        return None
    value = scores.get(label)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_by_day(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bucket: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        day = str(row["diagnosis_ts"])[:10]
        bucket[day]["total"] += 1
        bucket[day][row["status"]] += 1
        if row["status"] == "mismatch":
            pair = f"{row['db_label']}->{row['replay_label']}"
            bucket[day][pair] += 1
    summary = []
    for day in sorted(bucket):
        counts = bucket[day]
        item = {
            "day": day,
            "total": counts["total"],
            "match": counts["match"],
            "mismatch": counts["mismatch"],
            "error": counts["error"],
        }
        pairs = {key: value for key, value in counts.items() if "->" in key}
        item["top_pairs"] = dict(sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:8])
        summary.append(item)
    return summary


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_day_aggregators(scheduler: Any, days: list[str], baseline_days: int) -> dict[str, Any]:
    cache_dir = LOG_DIR / ".full115_replay_baselines"
    cache_dir.mkdir(parents=True, exist_ok=True)
    aggregators = {}
    for day in days:
        rows = scheduler.store.query_daily_baselines(day, baseline_days=baseline_days)
        meta = {
            row["variable_name"]: {
                "median_ref": float(row["median_ref"]),
                "iqr_ref": float(row["iqr_ref"]),
            }
            for row in rows
        }
        path = cache_dir / f"baseline_{day}.yaml"
        path.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=True), encoding="utf-8")
        aggregators[day] = scheduler.FeatureAggregator(str(path))
    return aggregators


def diagnose_fast(
    scheduler: Any,
    ts: datetime,
    wide: Any,
    aggregators: dict[str, Any],
    *,
    baseline_days: int,
    window_minutes: int,
    min_coverage: float,
) -> dict[str, Any]:
    window_start = ts - timedelta(minutes=window_minutes)
    window_end = ts
    current = wide[(wide["timestamp"] >= window_start) & (wide["timestamp"] <= window_end)].copy()
    coverage = scheduler.store.data_coverage(current, window_start, window_end, scheduler.required_variables)
    if float(coverage.get("coverage_ratio", 0.0)) < min_coverage:
        return {
            "timestamp": ts,
            "diagnosis_window_start": window_start,
            "diagnosis_window_end": window_end,
            "baseline_days": baseline_days,
            "window_minutes": window_minutes,
            "main_label": "data_quality_low",
            "main_score": 0.0,
            "main_confidence": 0.0,
            "secondary_label": None,
            "secondary_score": 0.0,
            "secondary_confidence": 0.0,
            "data_coverage": coverage,
            "raw_scores": {},
            "feature_snapshot": {},
        }
    day = ts.date().isoformat()
    aggregator = aggregators[day]
    features = aggregator.aggregate(current)
    engine = scheduler.DiagnosticEngine()
    result = engine.run(features, timestamp=ts.strftime("%Y-%m-%d %H:%M:%S"))
    return {
        **result,
        "timestamp": ts,
        "diagnosis_window_start": window_start,
        "diagnosis_window_end": window_end,
        "baseline_days": baseline_days,
        "window_minutes": window_minutes,
        "data_coverage": coverage,
        "feature_snapshot": features,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay full115 diagnosis and compare with stored snapshots.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15432)
    parser.add_argument("--database", default="bf_trend")
    parser.add_argument("--user", default="gl02_sync")
    parser.add_argument("--password", default="gl02_local_sync")
    parser.add_argument("--start", default="2026-04-14 00:00:00")
    parser.add_argument("--end", default="2026-05-15 00:00:00", help="Exclusive end timestamp.")
    parser.add_argument("--config", default=str(SERVICE_DIR / "config.yaml"))
    parser.add_argument("--out-prefix", default="full115_replay_compare_20260414_20260514")
    parser.add_argument("--limit", type=int, default=0, help="Debug only: compare first N points.")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument(
        "--slow-scheduler",
        action="store_true",
        help="Use AutoDiagnosisScheduler.diagnose_point for every point. Slower but useful for debugging.",
    )
    args = parser.parse_args()

    started = time.time()
    set_env(args)
    if str(SERVICE_DIR) not in sys.path:
        sys.path.insert(0, str(SERVICE_DIR))

    from diagnosis_scheduler import AutoDiagnosisScheduler  # type: ignore

    records = fetch_latest_snapshots(args)
    if not records:
        print("no snapshots found")
        return 1

    scheduler = AutoDiagnosisScheduler(args.config)
    scheduler.store.open_session()
    baseline_days = int(scheduler.diag_cfg["baseline_days"])
    window_minutes = int(scheduler.diag_cfg["window_minutes"])
    min_coverage = float(scheduler.diag_cfg.get("min_window_coverage_ratio", 0.75))

    wide = None
    aggregators: dict[str, Any] = {}
    if not args.slow_scheduler:
        data_start = parse_time(args.start) - timedelta(minutes=window_minutes)
        data_end = parse_time(args.end)
        print(
            json.dumps(
                {
                    "stage": "preload_wide_frame",
                    "start": data_start,
                    "end": data_end,
                    "rule_profile": "full115",
                },
                ensure_ascii=False,
                default=json_default,
            ),
            flush=True,
        )
        wide = scheduler.store.fetch_wide_frame(data_start, data_end, None)
        print(
            json.dumps(
                {
                    "stage": "preload_done",
                    "rows": len(wide),
                    "columns": len(getattr(wide, "columns", [])),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        days = sorted({record["diagnosis_ts"].date().isoformat() for record in records})
        aggregators = load_day_aggregators(scheduler, days, baseline_days)

    full_rows: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    try:
        total = len(records)
        for index, record in enumerate(records, 1):
            ts = record["diagnosis_ts"]
            if not isinstance(ts, datetime):
                ts = parse_time(str(ts))
            row: dict[str, Any] = {
                "index": index,
                "diagnosis_ts": ts,
                "db_id": record.get("id"),
                "db_label": record.get("main_label"),
                "db_score": record.get("main_score"),
                "db_secondary_label": record.get("secondary_label"),
                "db_secondary_score": record.get("secondary_score"),
                "db_rule_profile": (record.get("source") or {}).get("rule_profile") if isinstance(record.get("source"), dict) else "",
                "db_rule_profile_variables": (record.get("source") or {}).get("rule_profile_variables") if isinstance(record.get("source"), dict) else "",
                "db_updated_at": record.get("updated_at"),
            }
            try:
                if args.slow_scheduler:
                    replay = scheduler.diagnose_point(ts, dry_run=True)
                else:
                    replay = diagnose_fast(
                        scheduler,
                        ts,
                        wide,
                        aggregators,
                        baseline_days=baseline_days,
                        window_minutes=window_minutes,
                        min_coverage=min_coverage,
                    )
                replay_scores = replay.get("raw_scores") or {}
                row.update(
                    {
                        "replay_label": replay.get("main_label"),
                        "replay_score": replay.get("main_score"),
                        "replay_secondary_label": replay.get("secondary_label"),
                        "replay_secondary_score": replay.get("secondary_score"),
                        "replay_score_for_db_label": score_for(str(record.get("main_label") or ""), replay_scores),
                        "coverage_ratio": (replay.get("data_coverage") or {}).get("coverage_ratio"),
                        "replay_baseline_start": replay.get("baseline_window_start"),
                        "replay_baseline_end": replay.get("baseline_window_end"),
                        "replay_rule_profile": "full115",
                        "replay_raw_scores": json.dumps(replay_scores, ensure_ascii=False, default=json_default),
                    }
                )
                row["status"] = "match" if row["db_label"] == row["replay_label"] else "mismatch"
                if row["status"] == "mismatch":
                    mismatches.append(row.copy())
            except Exception as exc:  # noqa: BLE001
                row.update({"status": "error", "error": repr(exc)})
                errors.append(row.copy())
            full_rows.append(row)

            if args.progress_every and (index % args.progress_every == 0 or index == total):
                elapsed = time.time() - started
                rate = index / elapsed if elapsed > 0 else 0.0
                print(
                    json.dumps(
                        {
                            "progress": f"{index}/{total}",
                            "mismatches": len(mismatches),
                            "errors": len(errors),
                            "rate_points_per_sec": round(rate, 2),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    finally:
        scheduler.store.close_session()

    elapsed = time.time() - started
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": f"{args.host}:{args.port}/{args.database}",
        "window_start": args.start,
        "window_end_exclusive": args.end,
        "rule_profile": "full115",
        "total": len(full_rows),
        "match": sum(1 for row in full_rows if row["status"] == "match"),
        "mismatch": len(mismatches),
        "error": len(errors),
        "elapsed_seconds": round(elapsed, 2),
        "by_day": summarize_by_day(full_rows),
    }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    prefix = LOG_DIR / args.out_prefix
    full_csv = prefix.with_suffix(".full.csv")
    mismatch_csv = prefix.with_suffix(".mismatches.csv")
    summary_json = prefix.with_suffix(".summary.json")
    summary_md = prefix.with_suffix(".summary.md")
    full_jsonl = prefix.with_suffix(".full.jsonl")

    columns = [
        "index",
        "diagnosis_ts",
        "status",
        "db_label",
        "replay_label",
        "db_score",
        "replay_score",
        "replay_score_for_db_label",
        "db_secondary_label",
        "replay_secondary_label",
        "db_secondary_score",
        "replay_secondary_score",
        "coverage_ratio",
        "db_rule_profile",
        "db_rule_profile_variables",
        "replay_rule_profile",
        "replay_baseline_start",
        "replay_baseline_end",
        "db_updated_at",
        "db_id",
        "error",
        "replay_raw_scores",
    ]
    write_csv(full_csv, full_rows, columns)
    write_csv(mismatch_csv, mismatches + errors, columns)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, default=json_default, indent=2), encoding="utf-8")
    with full_jsonl.open("w", encoding="utf-8") as f:
        for row in full_rows:
            f.write(json.dumps(row, ensure_ascii=False, default=json_default) + "\n")

    lines = [
        "# full115 全量回放比对报告",
        "",
        f"- 生成时间：`{summary['generated_at']}`",
        f"- 数据库：`{summary['database']}`",
        f"- 窗口：`{args.start}` 到 `{args.end}`（不含结束）",
        f"- 总点数：`{summary['total']}`",
        f"- 一致：`{summary['match']}`",
        f"- 不一致：`{summary['mismatch']}`",
        f"- 错误：`{summary['error']}`",
        f"- 耗时秒：`{summary['elapsed_seconds']}`",
        "",
        "## 每日汇总",
        "",
        "| 日期 | 总点数 | 一致 | 不一致 | 错误 | 主要不一致方向 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in summary["by_day"]:
        pairs = ", ".join(f"{key}:{value}" for key, value in row["top_pairs"].items()) or ""
        lines.append(f"| {row['day']} | {row['total']} | {row['match']} | {row['mismatch']} | {row['error']} | {pairs} |")

    lines.extend(
        [
            "",
            "## 不一致明细",
            "",
            "| 时间 | 数据库炉况 | full115回放炉况 | 数据库分数 | 回放分数 | 覆盖率 | 数据库规则记录 |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in mismatches + errors:
        db_label = LABEL_CN.get(str(row.get("db_label")), str(row.get("db_label")))
        replay_label = LABEL_CN.get(str(row.get("replay_label")), str(row.get("replay_label") or row.get("error")))
        lines.append(
            "| {diagnosis_ts} | {db_label} | {replay_label} | {db_score} | {replay_score} | {coverage_ratio} | {profile} |".format(
                diagnosis_ts=json_default(row.get("diagnosis_ts")),
                db_label=db_label,
                replay_label=replay_label,
                db_score=row.get("db_score"),
                replay_score=row.get("replay_score"),
                coverage_ratio=row.get("coverage_ratio"),
                profile=row.get("db_rule_profile") or "未记录",
            )
        )
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "summary": summary,
                "summary_json": str(summary_json),
                "summary_md": str(summary_md),
                "mismatch_csv": str(mismatch_csv),
                "full_csv": str(full_csv),
                "full_jsonl": str(full_jsonl),
            },
            ensure_ascii=False,
            default=json_default,
            indent=2,
        ),
        flush=True,
    )
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
