# -*- coding: utf-8 -*-
"""Recompute daily furnace-condition distributions from PostgreSQL sensor data.

This script intentionally separates three profiles:

- persisted_db: labels already stored in bf_sensor.diagnosis_snapshots.
- core19: only the 19 variables declared by AutoDiagnosisScheduler.required_variables.
- full115: all enabled physical variables in bf_sensor.sensor_registry.

All recomputation uses bf_sensor.daily_baselines for the target day, keeping the
historical-baseline definition stable while comparing rule input profiles.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULE_ENGINE_DIR = PROJECT_ROOT / "炉况规则引擎"
if str(RULE_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(RULE_ENGINE_DIR))

from features.aggregator import FeatureAggregator  # noqa: E402
from main import DiagnosticEngine  # noqa: E402


CORE19 = [
    "P_blast",
    "P_blast_cold",
    "Q_blast",
    "P_top",
    "DP_upper",
    "DP_lower",
    "DP_total",
    "T_blast",
    "PCI_rate",
    "Q_O2",
    "PI",
    "GasUtil",
    "L",
    "L_south",
    "L_north",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
]

LABEL_CN = {
    "normal": "正常顺行",
    "cold": "炉凉",
    "hot": "炉热",
    "edge": "边缘气流",
    "center": "中心气流",
    "channel": "管道/偏行",
    "lowline": "低料线",
    "column": "悬料/料柱异常",
    "data_quality_low": "数据质量低",
    "unknown": "未知",
}


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("T", " ")).date()


def floor_to_interval(dt: datetime, minutes: int) -> datetime:
    return dt.replace(second=0, microsecond=0) - timedelta(minutes=dt.minute % minutes)


def daterange(start: date, end_exclusive: date):
    cur = start
    while cur < end_exclusive:
        yield cur
        cur += timedelta(days=1)


def connect(args: argparse.Namespace):
    return psycopg.connect(
        host=args.host or os.environ.get("GL02_PGHOST", "127.0.0.1"),
        port=int(args.port or os.environ.get("GL02_PGPORT", "5432")),
        dbname=args.database or os.environ.get("GL02_PGDATABASE", "bf_trend"),
        user=args.user or os.environ.get("GL02_PGUSER", "gl02_reader"),
        password=args.password or os.environ.get("GL02_PGPASSWORD"),
        connect_timeout=10,
    )


def load_enabled_variables(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT variable_name
            FROM bf_sensor.sensor_registry
            WHERE is_enabled = true AND is_derived = false
            ORDER BY variable_name
            """
        )
        return [r[0] for r in cur.fetchall()]


def load_baseline_meta(conn, baseline_day: date, baseline_days: int) -> dict[str, dict[str, float]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT variable_name, median_ref, iqr_ref
            FROM bf_sensor.daily_baselines
            WHERE baseline_day = %s AND baseline_days = %s
            """,
            (baseline_day, baseline_days),
        )
        return {
            str(name): {"median_ref": float(median), "iqr_ref": float(iqr)}
            for name, median, iqr in cur.fetchall()
            if median is not None and iqr not in (None, 0)
        }


def load_sensor_frame(conn, start: datetime, end: datetime, variables: list[str] | None) -> pd.DataFrame:
    params: list[Any] = [start, end]
    extra = ""
    if variables:
        extra = "AND r.variable_name = ANY(%s)"
        params.append(variables)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT r.variable_name, v.ts, v.value
            FROM bf_sensor.one_minute_values v
            JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
            WHERE r.is_enabled = true
              AND r.is_derived = false
              AND v.ts >= %s
              AND v.ts <= %s
              {extra}
            ORDER BY v.ts ASC, r.variable_name ASC
            """,
            params,
        )
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["timestamp"])
    df = pd.DataFrame(rows, columns=["variable_name", "ts", "value"])
    wide = df.pivot_table(index="ts", columns="variable_name", values="value", aggfunc="mean").sort_index()
    wide.index = pd.to_datetime(wide.index)
    wide = wide.reset_index().rename(columns={"ts": "timestamp"})
    for col in wide.columns:
        if col != "timestamp":
            wide[col] = pd.to_numeric(wide[col], errors="coerce")
    top_cols = [c for c in ["T_top_A", "T_top_B", "T_top_C", "T_top_D"] if c in wide.columns]
    if "T_top" not in wide.columns and top_cols:
        wide = pd.concat([wide, wide[top_cols].mean(axis=1).rename("T_top")], axis=1)
    return wide


def coverage(frame: pd.DataFrame, start: datetime, end: datetime, variables: list[str]) -> dict[str, Any]:
    expected = int((end - start).total_seconds() // 60) + 1
    if frame.empty or "timestamp" not in frame.columns:
        return {"expected_minutes": expected, "observed_minutes": 0, "coverage_ratio": 0.0}
    window = frame[(frame["timestamp"] >= start) & (frame["timestamp"] <= end)]
    observed = int(window["timestamp"].nunique())
    ratios = {}
    for var in variables:
        ratios[var] = float(window[var].notna().sum() / expected) if var in window.columns and expected else 0.0
    return {
        "expected_minutes": expected,
        "observed_minutes": observed,
        "coverage_ratio": float(observed / expected) if expected else 0.0,
        "variable_coverage": ratios,
    }


def persisted_distribution(conn, start: datetime, end: datetime, baseline_days: int, window_minutes: int) -> dict[str, Any]:
    by_day: dict[str, Counter] = defaultdict(Counter)
    body_by_day: dict[str, int] = defaultdict(int)
    total_by_day: dict[str, int] = defaultdict(int)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT diagnosis_ts::date AS day, main_label, count(*)
            FROM bf_sensor.diagnosis_snapshots
            WHERE diagnosis_ts >= %s AND diagnosis_ts <= %s
              AND baseline_days = %s AND window_minutes = %s
            GROUP BY diagnosis_ts::date, main_label
            ORDER BY day, main_label
            """,
            (start, end, baseline_days, window_minutes),
        )
        for day, label, count in cur.fetchall():
            by_day[day.isoformat()][label or "unknown"] += int(count)
        cur.execute(
            """
            SELECT diagnosis_ts::date AS day,
                   count(*) AS total,
                   count(*) FILTER (
                     WHERE feature_snapshot ? 'T_body_lower'
                        OR feature_snapshot ? 'T_body_middle'
                        OR feature_snapshot ? 'z60_T_body_lower'
                        OR feature_snapshot ? 'z60_T_body_middle'
                   ) AS has_body
            FROM bf_sensor.diagnosis_snapshots
            WHERE diagnosis_ts >= %s AND diagnosis_ts <= %s
              AND baseline_days = %s AND window_minutes = %s
            GROUP BY diagnosis_ts::date
            ORDER BY day
            """,
            (start, end, baseline_days, window_minutes),
        )
        for day, total, has_body in cur.fetchall():
            total_by_day[day.isoformat()] = int(total)
            body_by_day[day.isoformat()] = int(has_body)
    return {
        day: {
            "counts": dict(counter),
            "total": sum(counter.values()),
            "body_feature_rows": body_by_day.get(day, 0),
            "rows": total_by_day.get(day, sum(counter.values())),
        }
        for day, counter in by_day.items()
    }


def recompute_profile(
    conn,
    day: date,
    day_end: datetime,
    variables: list[str],
    baseline_days: int,
    window_minutes: int,
    interval_minutes: int,
    min_coverage: float,
) -> dict[str, Any]:
    baseline_meta = load_baseline_meta(conn, day, baseline_days)
    if not baseline_meta:
        return {"counts": {}, "total": 0, "skipped": "missing_baseline"}

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(baseline_meta, f, allow_unicode=True, sort_keys=True)
        baseline_path = f.name

    try:
        aggregator = FeatureAggregator(baseline_path)
        fetch_start = datetime.combine(day, time.min) - timedelta(minutes=window_minutes)
        frame = load_sensor_frame(conn, fetch_start, day_end, variables)
        counts: Counter = Counter()
        examples: dict[str, Any] = {}
        feature_counts: list[int] = []
        body_rows = 0

        ts = datetime.combine(day, time.min)
        while ts <= day_end:
            window_start = ts - timedelta(minutes=window_minutes)
            window = frame[(frame["timestamp"] >= window_start) & (frame["timestamp"] <= ts)].copy()
            cov = coverage(window, window_start, ts, CORE19)
            if float(cov["coverage_ratio"]) < min_coverage:
                label = "data_quality_low"
                result = {
                    "main_label": label,
                    "main_score": 0.0,
                    "evidence": [{"name": "window_coverage_low"}],
                    "raw_scores": {},
                }
                features = {}
            else:
                features = aggregator.aggregate(window)
                result = DiagnosticEngine().run(features, timestamp=ts.strftime("%Y-%m-%d %H:%M:%S"))
                label = result.get("main_label") or "unknown"
            counts[label] += 1
            feature_counts.append(len(features))
            if any(str(k).startswith("T_body") or str(k).startswith("z60_T_body") or str(k).startswith("zstd_T_body") for k in features):
                body_rows += 1
            examples[label] = {
                "timestamp": ts,
                "main_score": result.get("main_score"),
                "raw_scores": result.get("raw_scores"),
                "evidence": result.get("evidence"),
                "coverage_ratio": cov.get("coverage_ratio"),
                "feature_count": len(features),
            }
            ts += timedelta(minutes=interval_minutes)
        return {
            "counts": dict(counts),
            "total": sum(counts.values()),
            "body_feature_rows": body_rows,
            "avg_feature_count": round(sum(feature_counts) / len(feature_counts), 2) if feature_counts else 0,
            "examples": {k: v for k, v in sorted(examples.items())},
        }
    finally:
        Path(baseline_path).unlink(missing_ok=True)


def pct(count: int, total: int) -> float:
    return round(count * 100.0 / total, 2) if total else 0.0


def flatten_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    labels = ["normal", "cold", "hot", "edge", "center", "channel", "lowline", "column", "data_quality_low", "unknown"]
    for day, profiles in results["days"].items():
        for profile, info in profiles.items():
            total = int(info.get("total") or 0)
            row = {
                "day": day,
                "profile": profile,
                "total": total,
                "body_feature_rows": info.get("body_feature_rows", ""),
                "avg_feature_count": info.get("avg_feature_count", ""),
            }
            counts = info.get("counts") or {}
            for label in labels:
                n = int(counts.get(label, 0))
                row[f"{label}_n"] = n
                row[f"{label}_pct"] = pct(n, total)
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="")
    parser.add_argument("--port", default="")
    parser.add_argument("--database", default="")
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--start-day", default="2026-05-01")
    parser.add_argument("--end-day", default="2026-05-14", help="Exclusive end day.")
    parser.add_argument("--baseline-days", type=int, default=30)
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--interval-minutes", type=int, default=5)
    parser.add_argument("--min-coverage", type=float, default=0.75)
    parser.add_argument("--profiles", default="core19,full115")
    parser.add_argument("--out-json", default=str(PROJECT_ROOT / "output" / "may_diagnosis_distribution_recomputed.json"))
    parser.add_argument("--out-csv", default=str(PROJECT_ROOT / "output" / "may_diagnosis_distribution_recomputed.csv"))
    args = parser.parse_args()

    start_day = parse_date(args.start_day)
    end_day = parse_date(args.end_day)
    profiles = {x.strip() for x in args.profiles.split(",") if x.strip()}

    with connect(args) as conn:
        latest_data_ts = None
        with conn.cursor() as cur:
            cur.execute("SELECT max(ts) FROM bf_sensor.one_minute_values")
            latest_data_ts = cur.fetchone()[0]
        if latest_data_ts is None:
            raise SystemExit("No sensor data found.")
        latest_floor = floor_to_interval(latest_data_ts, args.interval_minutes)
        all_vars = load_enabled_variables(conn)

        overall_start = datetime.combine(start_day, time.min)
        overall_end = min(datetime.combine(end_day, time.min) - timedelta(minutes=args.interval_minutes), latest_floor)
        persisted = persisted_distribution(conn, overall_start, overall_end, args.baseline_days, args.window_minutes)

        results: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "source": {
                "host": args.host or os.environ.get("GL02_PGHOST", "127.0.0.1"),
                "port": int(args.port or os.environ.get("GL02_PGPORT", "5432")),
                "database": args.database or os.environ.get("GL02_PGDATABASE", "bf_trend"),
                "schema": "bf_sensor",
            },
            "definition": {
                "baseline_table": "bf_sensor.daily_baselines",
                "baseline_days": args.baseline_days,
                "window_minutes": args.window_minutes,
                "interval_minutes": args.interval_minutes,
                "min_coverage": args.min_coverage,
                "core19_variables": CORE19,
                "full115_variable_count": len(all_vars),
            },
            "range": {
                "start_day": start_day.isoformat(),
                "end_day_exclusive": end_day.isoformat(),
                "latest_data_ts": latest_data_ts,
                "effective_end_ts": overall_end,
            },
            "days": {},
        }

        for day in daterange(start_day, end_day):
            day_start = datetime.combine(day, time.min)
            if day_start > overall_end:
                break
            day_end = min(datetime.combine(day + timedelta(days=1), time.min) - timedelta(minutes=args.interval_minutes), overall_end)
            day_key = day.isoformat()
            results["days"][day_key] = {
                "persisted_db": persisted.get(day_key, {"counts": {}, "total": 0}),
            }
            if "core19" in profiles:
                results["days"][day_key]["recompute_core19"] = recompute_profile(
                    conn,
                    day,
                    day_end,
                    CORE19,
                    args.baseline_days,
                    args.window_minutes,
                    args.interval_minutes,
                    args.min_coverage,
                )
            if "full115" in profiles:
                results["days"][day_key]["recompute_full115"] = recompute_profile(
                    conn,
                    day,
                    day_end,
                    all_vars,
                    args.baseline_days,
                    args.window_minutes,
                    args.interval_minutes,
                    args.min_coverage,
                )

    out_json = Path(args.out_json)
    out_csv = Path(args.out_csv)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    rows = flatten_rows(results)
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["day", "profile"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"ok": True, "json": str(out_json), "csv": str(out_csv), "days": len(results["days"])}, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
