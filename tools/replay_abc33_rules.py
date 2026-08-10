"""Read-only historical audit of reusable ABC common features.

REQ-ABC33-COMMON-FEATURES-20260808.  This command intentionally does not
evaluate A/B/C rules, generate alerts, write the database, or alter the live
release gate.  It audits z60_X, z15std_X, slope30_X and composite-factor
availability/distributions at a five-minute cadence.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
SERVICE = Path(os.environ.get("ABC33_SERVICE_ROOT") or (ROOT / "自动诊断服务"))
sys.path.insert(0, str(SERVICE))
if os.environ.get("ABC33_PATCH_ROOT"):
    sys.path.insert(0, os.environ["ABC33_PATCH_ROOT"])
from abc_feature_builder import build_feature_snapshot  # noqa: E402
from abc_rule_engine import evaluate, load_config  # noqa: E402

STANDARD_PREFIXES = ("z60_", "z15std_", "slope30_")
RAW_META_KEYS = {"timestamps", "evaluation_ts"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ABC reusable common-feature read-only replay")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--hours", type=float, help="small-window dry-run; overrides --days")
    parser.add_argument("--step-minutes", type=int, default=5)
    parser.add_argument("--max-batches", type=int, help="stop after N evaluation points")
    parser.add_argument("--max-samples-per-feature", type=int, default=10000,
                        help="bounded percentile reservoir per feature")
    parser.add_argument("--evaluate-rules-shadow", action="store_true",
                        help="offline-only A/B/C evaluation; never publishes scores or alerts")
    parser.add_argument("--end", help="ISO evaluation end; default is latest database minute")
    parser.add_argument("--output", default="logs/abc33_common_feature_replay_latest.json")
    return parser.parse_args()


def connection_string() -> str:
    host = os.getenv("GL02_PGHOST", os.getenv("PGHOST", "10.30.220.12"))
    port = os.getenv("GL02_PGPORT", os.getenv("PGPORT", "5432"))
    database = os.getenv("GL02_PGDATABASE", os.getenv("PGDATABASE", "bf_trend"))
    user = os.getenv("GL02_PGUSER", os.getenv("PGUSER"))
    password = os.getenv("GL02_PGPASSWORD", os.getenv("PGPASSWORD"))
    if not user or not password:
        raise RuntimeError("GL02_PGUSER/GL02_PGPASSWORD (or PGUSER/PGPASSWORD) are required")
    return f"host={host} port={port} dbname={database} user={user} password={password} connect_timeout=10"


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _load_baseline(conn, day) -> tuple[Any, dict[str, dict[str, Any]]]:
    selected = conn.execute(
        """SELECT max(baseline_day) AS day FROM bf_sensor.daily_baselines
           WHERE baseline_days=30 AND baseline_day <= %s""",
        (day,),
    ).fetchone()["day"]
    if selected is None:
        return None, {}
    rows = conn.execute(
        """SELECT variable_name,median_ref,iqr_ref,p25,p75,coverage_ratio,
                  sample_count,baseline_day,baseline_window_start,baseline_window_end
           FROM bf_sensor.daily_baselines
           WHERE baseline_days=30 AND baseline_day=%s""",
        (selected,),
    ).fetchall()
    return selected, {str(row["variable_name"]): dict(row) for row in rows}


def _load_chunk(conn, start: datetime, end: datetime, tag_to_var: dict[str, str]):
    rows = conn.execute(
        """SELECT tag_long_name,date_trunc('minute',ts) AS minute_ts,avg(value) AS value
           FROM bf_sensor.one_minute_values
           WHERE ts >= %s AND ts <= %s AND tag_long_name = ANY(%s)
           GROUP BY tag_long_name,date_trunc('minute',ts)
           ORDER BY minute_ts""",
        (start - timedelta(minutes=89), end, sorted(tag_to_var)),
    ).fetchall()
    by_var: dict[str, list[tuple[datetime, float | None]]] = defaultdict(list)
    for row in rows:
        variable = tag_to_var.get(str(row["tag_long_name"]))
        if variable:
            by_var[variable].append((row["minute_ts"], _finite(row["value"])))
    return {name: ([item[0] for item in values], values) for name, values in by_var.items()}


def _window(indexed, anchor: datetime) -> tuple[dict[str, Any], dict[str, Any], float | None]:
    timestamps = [anchor.replace(second=0, microsecond=0) - timedelta(minutes=89-index) for index in range(90)]
    history: dict[str, Any] = {"timestamps": [item.isoformat(sep=" ") for item in timestamps], "evaluation_ts": anchor.isoformat()}
    current: dict[str, Any] = {}
    ages: list[float] = []
    begin = timestamps[0]
    for name, (sample_times, rows) in indexed.items():
        left, right = bisect.bisect_left(sample_times, begin), bisect.bisect_right(sample_times, anchor)
        selected = rows[left:right]
        bucket = {stamp: value for stamp, value in selected}
        history[name] = [bucket.get(stamp) for stamp in timestamps]
        for stamp, value in reversed(selected):
            if value is None:
                continue
            age = max(0.0, (anchor-stamp).total_seconds())
            if age <= 300:
                current[name] = value
                ages.append(age)
            break
    return current, history, max(ages) if ages else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered)-1)*fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper]-ordered[lower])*(position-lower)


def main() -> int:
    args = arguments()
    duration = timedelta(hours=args.hours) if args.hours is not None else timedelta(days=args.days)
    if duration.total_seconds() <= 0 or args.step_minutes < 1 or args.max_samples_per_feature < 10:
        raise SystemExit("duration/step must be positive and sample reservoir must be >=10")
    config = load_config(SERVICE / "config" / "abc_furnace_rules.v1.json")
    values: dict[str, list[float]] = defaultdict(list)
    extrema: dict[str, list[float]] = {}
    available_batches: Counter[str] = Counter()
    seen_common_keys: set[str] = set()
    baseline_audit: list[dict[str, Any]] = []
    error_counts: Counter[str] = Counter()
    error_examples: list[dict[str, str]] = []
    rule_scores: dict[str, list[float]] = defaultdict(list)
    rule_confidence: dict[str, list[float]] = defaultdict(list)
    rule_computable: Counter[str] = Counter()
    rule_missing: dict[str, Counter[str]] = defaultdict(Counter)
    shadow_hits: Counter[str] = Counter()
    active_minutes: Counter[str] = Counter()
    maximum_active_minutes: Counter[str] = Counter()
    batches = 0
    attempted_batches = 0
    stopped_by_limit = False
    with psycopg.connect(connection_string(), row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        latest = conn.execute("SELECT max(ts) AS ts FROM bf_sensor.one_minute_values").fetchone()["ts"]
        end = datetime.fromisoformat(args.end) if args.end else latest
        if end is None:
            raise RuntimeError("bf_sensor.one_minute_values is empty")
        end = end.replace(second=0, microsecond=0)
        start = end - duration
        registry = conn.execute(
            """SELECT variable_name,tag_long_name FROM bf_sensor.sensor_registry
               WHERE is_enabled=true AND is_derived=false"""
        ).fetchall()
        tag_to_var = {str(row["tag_long_name"]): str(row["variable_name"]) for row in registry}
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(end, chunk_start.replace(hour=23, minute=59, second=0, microsecond=0))
            try:
                indexed = _load_chunk(conn, chunk_start, chunk_end, tag_to_var)
                baseline_day, baseline = _load_baseline(conn, chunk_start.date())
            except Exception as exc:
                name = type(exc).__name__
                error_counts[f"chunk:{name}"] += 1
                if len(error_examples) < 20:
                    error_examples.append({"scope": "chunk", "timestamp": chunk_start.isoformat(), "error_type": name})
                print(json.dumps({"day": str(chunk_start.date()), "state": "error", "error_type": name}), file=sys.stderr, flush=True)
                chunk_start = chunk_end + timedelta(minutes=1)
                continue
            baseline_rows = list(baseline.values())
            for variable in baseline:
                seen_common_keys.update(f"{prefix}{variable}" for prefix in STANDARD_PREFIXES)
            baseline_audit.append({
                "evaluation_day": str(chunk_start.date()),
                "selected_baseline_day": str(baseline_day) if baseline_day is not None else None,
                "fallback_days": (chunk_start.date()-baseline_day).days if baseline_day is not None else None,
                "variable_count": len(baseline),
                "window_start": min((row.get("baseline_window_start") for row in baseline_rows if row.get("baseline_window_start")), default=None),
                "window_end": max((row.get("baseline_window_end") for row in baseline_rows if row.get("baseline_window_end")), default=None),
            })
            anchor = chunk_start
            while anchor <= chunk_end:
                if args.max_batches is not None and attempted_batches >= args.max_batches:
                    stopped_by_limit = True
                    break
                attempted_batches += 1
                try:
                    current, history, age = _window(indexed, anchor)
                    features, quality = build_feature_snapshot(
                        current,
                        baseline=baseline,
                        history=history,
                        data_age_seconds=age,
                        coverage_ratio=1.0,
                        thresholds=config.get("feature_thresholds") or {},
                    )
                    common_keys = [key for key in features if key.startswith(STANDARD_PREFIXES) or key not in current]
                    seen_common_keys.update(common_keys)
                    for key in common_keys:
                        value = _finite(features.get(key))
                        if value is None:
                            continue
                        available_batches[key] += 1
                        if key not in extrema:
                            extrema[key] = [value, value]
                        else:
                            extrema[key][0] = min(extrema[key][0], value)
                            extrema[key][1] = max(extrema[key][1], value)
                        reservoir = values[key]
                        if len(reservoir) < args.max_samples_per_feature:
                            reservoir.append(value)
                        else:
                            # Deterministic bounded systematic replacement.
                            seen = available_batches[key]
                            slot = seen % args.max_samples_per_feature
                            if seen % max(1, seen // args.max_samples_per_feature) == 0:
                                reservoir[slot] = value
                    if args.evaluate_rules_shadow:
                        # Keep the production shadow configuration untouched.
                        # Internal evaluations always retain their calculated
                        # score; public serialization remains closed by the
                        # config's release_control gate.
                        bundle = evaluate(features, quality=quality, timestamp=anchor, config=config)
                        minimum_confidence = float(config["quality"]["minimum_coverage_ratio"])
                        hit_now: set[str] = set()
                        for item in bundle.get("evaluations", []):
                            rule_id = str(item["rule_id"])
                            confidence_value = _finite(item.get("confidence")) or 0.0
                            rule_confidence[rule_id].append(confidence_value)
                            for factor in item.get("missing_features") or []:
                                rule_missing[rule_id][str(factor)] += 1
                            score_value = _finite(item.get("score"))
                            computable = score_value is not None and confidence_value >= minimum_confidence
                            if not computable:
                                continue
                            rule_computable[rule_id] += 1
                            rule_scores[rule_id].append(score_value)
                            category = str(item.get("category") or rule_id[:1])
                            threshold = 55.0 if category == "B" else 70.0 if category == "C" else None
                            if threshold is not None and score_value >= threshold:
                                shadow_hits[rule_id] += 1
                                hit_now.add(rule_id)
                        for rule_id in [f"B{i}" for i in range(1, 14)] + [f"C{i}" for i in range(1, 12)]:
                            active_minutes[rule_id] = active_minutes[rule_id] + args.step_minutes if rule_id in hit_now else 0
                            maximum_active_minutes[rule_id] = max(maximum_active_minutes[rule_id], active_minutes[rule_id])
                    batches += 1
                except Exception as exc:
                    name = type(exc).__name__
                    error_counts[f"evaluation:{name}"] += 1
                    if len(error_examples) < 20:
                        error_examples.append({"scope": "evaluation", "timestamp": anchor.isoformat(), "error_type": name})
                anchor += timedelta(minutes=args.step_minutes)
            print(json.dumps({
                "day": str(chunk_start.date()), "state": "completed", "attempted_batches": attempted_batches,
                "successful_batches": batches, "errors": sum(error_counts.values()), "baseline_day": str(baseline_day) if baseline_day else None,
            }, ensure_ascii=False), file=sys.stderr, flush=True)
            if stopped_by_limit:
                break
            chunk_start = chunk_end + timedelta(minutes=1)
    feature_summary = {}
    for key in sorted(values):
        series = values[key]
        feature_summary[key] = {
            "available_batches": available_batches[key],
            "missing_batches": max(0, batches-available_batches[key]),
            "coverage_ratio": round(available_batches[key]/batches, 6) if batches else 0.0,
            "percentile_sample_count": len(series),
            "percentiles_are_sampled": available_batches[key] > len(series),
            "min": extrema[key][0], "p05": _percentile(series, .05), "median": _percentile(series, .5),
            "p95": _percentile(series, .95), "max": extrema[key][1],
        }
    for key in sorted(seen_common_keys-set(feature_summary)):
        feature_summary[key] = {
            "available_batches": 0, "missing_batches": batches, "coverage_ratio": 0.0,
            "percentile_sample_count": 0, "percentiles_are_sampled": False,
            "min": None, "p05": None, "median": None, "p95": None, "max": None,
        }
    standard = {key: value for key, value in feature_summary.items() if key.startswith(STANDARD_PREFIXES)}
    composite = {key: value for key, value in feature_summary.items() if not key.startswith(STANDARD_PREFIXES)}
    rule_shadow = {}
    if args.evaluate_rules_shadow:
        for category, count in (("A", 9), ("B", 13), ("C", 11)):
            for index in range(1, count+1):
                rule_id = f"{category}{index}"
                scores = rule_scores.get(rule_id, [])
                confidences = rule_confidence.get(rule_id, [])
                rule_shadow[rule_id] = {
                    "computable_batches": rule_computable[rule_id],
                    "not_computable_batches": max(0, batches-rule_computable[rule_id]),
                    "computable_ratio": round(rule_computable[rule_id]/batches, 6) if batches else 0.0,
                    "confidence_p05": _percentile(confidences, .05),
                    "confidence_median": _percentile(confidences, .5),
                    "confidence_p95": _percentile(confidences, .95),
                    "score_p05": _percentile(scores, .05), "score_median": _percentile(scores, .5),
                    "score_p95": _percentile(scores, .95), "score_max": max(scores) if scores else None,
                    "shadow_threshold": 55.0 if category == "B" else 70.0 if category == "C" else None,
                    "shadow_threshold_hit_batches": shadow_hits[rule_id] if category in {"B", "C"} else None,
                    "maximum_continuous_shadow_hit_minutes": maximum_active_minutes[rule_id] if category in {"B", "C"} else None,
                    "missing_factors": dict(rule_missing[rule_id].most_common()),
                }
    report = {
        "schema_version": "abc33.common-feature-replay.v1",
        "requirement_id": "REQ-ABC33-COMMON-FEATURES-20260808",
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "step_minutes": args.step_minutes, "attempted_batches": attempted_batches, "successful_batches": batches,
        "stopped_by_max_batches": stopped_by_limit,
        "max_samples_per_feature": args.max_samples_per_feature,
        "baseline_day_audit": baseline_audit,
        "error_counts": dict(error_counts), "error_examples": error_examples,
        "standard_features": standard, "composite_factors": composite,
        "rule_shadow_evaluation_enabled": bool(args.evaluate_rules_shadow),
        "rule_shadow_evaluations": rule_shadow,
        "production_scores_opened": False, "production_alerts_opened": False,
        "alerts": False, "database_writes": 0,
    }
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"output": str(target), "attempted_batches": attempted_batches, "successful_batches": batches,
                      "errors": sum(error_counts.values()), "standard_features": len(standard), "composite_factors": len(composite)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
