from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from baseline_maintainer import build_day
from baseline_service import build_baseline_meta, write_runtime_baseline
from abc_burden_rate import fetch_burden_rate_snapshot
from abc_feature_builder import build_feature_snapshot
from abc_rule_engine import evaluate as evaluate_abc, load_config as load_abc_config
from service_config import PROJECT_ROOT, load_config, project_path
from store import DiagnosisStore


SERVICE_DIR = Path(__file__).resolve().parent


CORE19_VARIABLES = [
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


def build_abc_runtime_inputs(frame: pd.DataFrame, evaluation_ts: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a 90-minute, minute-aligned production input contract.

    Current values come exclusively from the final common minute.  This avoids
    constructing top-temperature/top-pressure ranges from asynchronously aged
    sensor samples.  Missing minutes remain null in history for the 75% window
    coverage gates.
    """
    end = pd.Timestamp(evaluation_ts).floor("min")
    index = pd.date_range(end=end, periods=90, freq="min")
    if frame.empty or "timestamp" not in frame.columns:
        return {}, {"timestamps": [item.isoformat() for item in index], "evaluation_ts": end.isoformat()}
    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"]).dt.floor("min")
    working = working[working["timestamp"] <= end]
    working = working.groupby("timestamp", as_index=True).mean(numeric_only=True).reindex(index)
    history: dict[str, Any] = {
        "timestamps": [item.isoformat() for item in index],
        "evaluation_ts": end.isoformat(),
    }
    for column in working.columns:
        history[str(column)] = [None if pd.isna(value) else float(value) for value in working[column].tolist()]
    final = working.iloc[-1]
    current = {str(column): float(value) for column, value in final.items() if not pd.isna(value)}
    return current, history


def resolve_rule_engine_dir(configured: str | Path | None) -> Path:
    configured_path = project_path(configured or "rule_engine")
    candidates = [
        configured_path,
        PROJECT_ROOT / "炉况规则引擎",
        PROJECT_ROOT / "rule_engine",
    ]
    checked: list[Path] = []
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in checked:
            continue
        checked.append(candidate)
        if (candidate / "features" / "aggregator.py").exists() and (candidate / "main.py").exists():
            return candidate
    checked_text = "; ".join(str(path) for path in checked)
    raise FileNotFoundError(
        f"Rule engine directory is invalid. Expected features/aggregator.py and main.py; "
        f"configured paths.rule_engine_dir={configured!r}; checked: {checked_text}"
    )


def floor_to_interval(dt: datetime, minutes: int) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    remainder = dt.minute % minutes
    return dt - timedelta(minutes=remainder)


def iter_points(start: datetime, end: datetime, step_minutes: int):
    cursor = floor_to_interval(start, step_minutes)
    if cursor < start:
        cursor += timedelta(minutes=step_minutes)
    while cursor <= end:
        yield cursor
        cursor += timedelta(minutes=step_minutes)


def json_safe_feature_snapshot(features: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in features.items():
        if isinstance(value, (pd.Series, pd.DataFrame)):
            continue
        if isinstance(value, (str, bool)) or value is None:
            out[key] = value
            continue
        try:
            number = float(value)
        except Exception:
            continue
        if math.isfinite(number):
            out[key] = round(number, 6)
    return out


class AutoDiagnosisScheduler:
    def __init__(self, config_path: str | Path | None = None):
        self.config = load_config(config_path) if config_path else load_config()
        self.store = DiagnosisStore(config_path)
        self.diag_cfg = self.config["diagnosis"]
        rule_engine_dir = resolve_rule_engine_dir(self.config.get("paths", {}).get("rule_engine_dir"))
        if str(rule_engine_dir) not in sys.path:
            sys.path.insert(0, str(rule_engine_dir))
        from features.aggregator import FeatureAggregator
        from main import DiagnosticEngine

        self.FeatureAggregator = FeatureAggregator
        self.DiagnosticEngine = DiagnosticEngine
        self._baseline_cache: dict[tuple[str, int], dict[str, Any]] = {}
        self._latest_data_ts_cache: datetime | None | object = None

    @property
    def required_variables(self) -> list[str]:
        return list(CORE19_VARIABLES)

    @property
    def rule_profile(self) -> str:
        value = os.environ.get("GL02_RULE_PROFILE") or self.diag_cfg.get("rule_profile") or "core19"
        value = str(value).strip().lower()
        if value not in {"core19", "full115"}:
            raise ValueError(f"Unsupported diagnosis rule_profile: {value!r}; expected core19 or full115")
        return value

    @property
    def diagnosis_variables(self) -> list[str] | None:
        if self.rule_profile == "full115":
            return None
        return self.required_variables

    def latest_complete_target(self, reference: datetime | None = None, *, wait: bool = False) -> tuple[datetime | None, dict[str, Any]]:
        interval = int(self.diag_cfg["diagnosis_interval_minutes"])
        candidate = floor_to_interval(reference or datetime.now(), interval)
        timeout = float(self.diag_cfg.get("sync_wait_timeout_seconds", 0) or 0)
        poll = max(1.0, float(self.diag_cfg.get("sync_wait_poll_seconds", 15) or 15))
        started = time.time()
        latest_ts = self.store.latest_data_ts()
        waited = 0.0
        while wait and latest_ts is not None and latest_ts < candidate and (time.time() - started) < timeout:
            time.sleep(poll)
            latest_ts = self.store.latest_data_ts()
            waited = time.time() - started
        if latest_ts is None:
            return None, {
                "candidate_target": candidate,
                "latest_data_ts": None,
                "waited_seconds": round(waited, 1),
                "status": "no_source_data",
            }
        capped = min(candidate, floor_to_interval(latest_ts, interval))
        return capped, {
            "candidate_target": candidate,
            "latest_data_ts": latest_ts,
            "target": capped,
            "waited_seconds": round(waited, 1),
            "status": "ready" if latest_ts >= candidate else "capped_to_latest_data",
        }

    def find_diagnosis_work_points(self, start: datetime, end: datetime, *, include_invalid: bool = True) -> tuple[list[datetime], dict[str, Any]]:
        return self.store.find_missing_or_invalid_diagnosis_points(
            start,
            end,
            step_minutes=int(self.diag_cfg["diagnosis_interval_minutes"]),
            window_minutes=int(self.diag_cfg["window_minutes"]),
            required_variables=self.required_variables,
            min_coverage_ratio=float(self.diag_cfg.get("min_window_coverage_ratio", 0.75)),
            include_invalid=include_invalid,
        )

    def diagnose_point(self, ts: datetime, dry_run: bool = False) -> dict[str, Any]:
        abc_config = load_abc_config()
        abc_thresholds = abc_config.get("feature_thresholds") or {}
        baseline_days = int(self.diag_cfg["baseline_days"])
        window_minutes = int(self.diag_cfg["window_minutes"])
        interval = int(self.diag_cfg["diagnosis_interval_minutes"])
        if self.diag_cfg.get("enforce_sync_barrier", True) and not self.store.local_csv_path:
            latest_data_ts = self.store.latest_data_ts()
            if latest_data_ts is None or ts > floor_to_interval(latest_data_ts, interval):
                return {
                    "timestamp": ts,
                    "skipped": True,
                    "reason": "sync_pending",
                    "latest_data_ts": latest_data_ts,
                    "main_label": "sync_pending",
                    "main_score": 0.0,
                    "main_confidence": 0.0,
                    "secondary_label": None,
                    "secondary_score": 0.0,
                    "secondary_confidence": 0.0,
                    "evidence": [
                        {
                            "name": "sync_pending",
                            "text": "诊断目标时间晚于本地1min同步库最新时间，等待同步完成后再计算。",
                        }
                    ],
                    "raw_scores": {},
                    "feature_snapshot": {},
                }
        baseline_end = ts - timedelta(minutes=window_minutes)
        baseline_start = baseline_end - timedelta(days=baseline_days)
        window_start = ts - timedelta(minutes=window_minutes)
        window_end = ts

        baseline_day = ts.date()
        persisted_baseline = {}
        if not self.store.local_csv_path:
            try:
                cache_key = (baseline_day.isoformat(), baseline_days)
                if cache_key not in self._baseline_cache:
                    baseline_rows = self.store.query_daily_baselines(baseline_day, baseline_days=baseline_days)
                    if not baseline_rows:
                        build_day(baseline_day, baseline_days=baseline_days, write=not dry_run)
                        baseline_rows = self.store.query_daily_baselines(baseline_day, baseline_days=baseline_days)
                    self._baseline_cache[cache_key] = {
                        "meta": {
                            row["variable_name"]: {
                                "median_ref": float(row["median_ref"]),
                                "iqr_ref": float(row["iqr_ref"]),
                                "coverage_ratio": float(row["coverage_ratio"]) if row.get("coverage_ratio") is not None else None,
                                "sample_count": int(row["sample_count"]) if row.get("sample_count") is not None else None,
                                "expected_minutes": int(row["expected_minutes"]) if row.get("expected_minutes") is not None else None,
                            }
                            for row in baseline_rows
                        },
                        "window_start": min((row["baseline_window_start"] for row in baseline_rows), default=None),
                        "window_end": max((row["baseline_window_end"] for row in baseline_rows), default=None),
                    }
                cached_baseline = self._baseline_cache[cache_key]
                persisted_baseline = cached_baseline.get("meta") or {}
                if cached_baseline.get("window_start") and cached_baseline.get("window_end"):
                    baseline_start = cached_baseline["window_start"]
                    baseline_end = cached_baseline["window_end"]
                if not persisted_baseline:
                    build_day(baseline_day, baseline_days=baseline_days, write=not dry_run)
                    self._baseline_cache.pop(cache_key, None)
                    baseline_rows = self.store.query_daily_baselines(baseline_day, baseline_days=baseline_days)
                    persisted_baseline = {
                        row["variable_name"]: {
                            "median_ref": float(row["median_ref"]),
                            "iqr_ref": float(row["iqr_ref"]),
                            "coverage_ratio": float(row["coverage_ratio"]) if row.get("coverage_ratio") is not None else None,
                            "sample_count": int(row["sample_count"]) if row.get("sample_count") is not None else None,
                            "expected_minutes": int(row["expected_minutes"]) if row.get("expected_minutes") is not None else None,
                        }
                        for row in baseline_rows
                    }
                    if baseline_rows:
                        baseline_start = min(row["baseline_window_start"] for row in baseline_rows)
                        baseline_end = max(row["baseline_window_end"] for row in baseline_rows)
            except Exception:
                persisted_baseline = {}
        diagnosis_variables = self.diagnosis_variables
        history = (
            self.store.fetch_wide_frame(baseline_start, baseline_end, diagnosis_variables)
            if not persisted_baseline
            else pd.DataFrame()
        )
        current = self.store.fetch_wide_frame(window_start, window_end, diagnosis_variables)
        abc_frame = self.store.fetch_wide_frame(ts - timedelta(minutes=89), ts, None)
        abc_current_values, abc_history_values = build_abc_runtime_inputs(abc_frame, ts)
        try:
            with self.store.connection_scope() as burden_conn:
                burden_snapshot = fetch_burden_rate_snapshot(burden_conn, ts, abc_thresholds.get("burden_rate"))
            abc_current_values.update(burden_snapshot.get("values") or {})
        except Exception as exc:
            print(f"ABC burden-rate source unavailable: {type(exc).__name__}", file=sys.stderr)
        latest_ts = self.store.latest_data_ts()
        lag = int((datetime.now().replace(tzinfo=None) - latest_ts).total_seconds()) if latest_ts else None
        coverage = self.store.data_coverage(current, window_start, window_end, self.required_variables)
        missing = [name for name, ratio in coverage.get("variable_coverage", {}).items() if ratio <= 0]
        min_coverage = float(self.diag_cfg.get("min_window_coverage_ratio", 0.75))
        source = (
            {"type": "local_wide_csv", "path": self.store.local_csv_path, "read_policy": "dry_run_local_demo"}
            if self.store.local_csv_path
            else dict(self.config["source"])
        )
        source["rule_profile"] = self.rule_profile
        source["rule_profile_variables"] = len(self.required_variables) if diagnosis_variables else "all_enabled_physical"
        base_payload = {
            "timestamp": ts,
            "diagnosis_window_start": window_start,
            "diagnosis_window_end": window_end,
            "baseline_window_start": baseline_start,
            "baseline_window_end": baseline_end,
            "baseline_days": baseline_days,
            "window_minutes": window_minutes,
            "source": source,
            "data_coverage": coverage,
            "missing_variables": missing,
            "source_lag_seconds": lag,
        }
        if float(coverage.get("coverage_ratio", 0.0)) < min_coverage:
            low_features, low_quality = build_feature_snapshot(
                abc_current_values,
                baseline=persisted_baseline,
                history=abc_history_values,
                data_age_seconds=lag,
                coverage_ratio=float(coverage.get("coverage_ratio", 0.0)),
                thresholds=abc_thresholds,
            )
            try:
                low_abc_bundle = evaluate_abc(low_features, quality=low_quality, timestamp=ts, config=abc_config)
            except Exception as exc:
                low_abc_bundle = {"schema_version": "abc_rule_bundle.v1", "state": "error", "error_type": type(exc).__name__}
            payload = {
                **base_payload,
                "main_label": "data_quality_low",
                "main_score": 0.0,
                "main_confidence": 0.0,
                "secondary_label": None,
                "secondary_score": 0.0,
                "secondary_confidence": 0.0,
                "subtype": "insufficient_window_coverage",
                "evidence": [
                    {
                        "name": "window_coverage_low",
                        "text": (
                            f"Current window coverage {coverage.get('coverage_ratio', 0.0):.2%} "
                            f"is below threshold {min_coverage:.2%}; skip furnace-condition inference."
                        ),
                    }
                ],
                "raw_scores": {},
                "feature_snapshot": {},
                "abc_rule_bundle_internal": low_abc_bundle,
            }
            if not dry_run:
                self.store.upsert_diagnosis(payload)
                if low_abc_bundle.get("evaluations"):
                    self.store.persist_abc_evaluation(low_abc_bundle, source_snapshot_id=None)
            return payload
        baseline_meta = persisted_baseline or build_baseline_meta(history)
        baseline_path = write_runtime_baseline(baseline_meta)
        aggregator = self.FeatureAggregator(str(baseline_path))
        features = aggregator.aggregate(current)
        engine = self.DiagnosticEngine()
        result = engine.run(features, timestamp=ts.strftime("%Y-%m-%d %H:%M:%S"))

        # ABC33 runs in parallel with the legacy eight-condition engine.  The
        # complete evaluation is retained server-side; the WebSocket/API layer
        # must serialize only ``abc_bundle.public``.
        abc_features, abc_quality = build_feature_snapshot(
            {**abc_current_values, **json_safe_feature_snapshot(features)},
            baseline=persisted_baseline,
            history=abc_history_values,
            data_age_seconds=lag,
            coverage_ratio=float(coverage.get("coverage_ratio", 0.0)),
            thresholds=abc_thresholds,
        )
        try:
            abc_bundle = evaluate_abc(abc_features, quality=abc_quality, timestamp=ts, config=abc_config)
        except Exception as exc:
            abc_bundle = {"schema_version": "abc_rule_bundle.v1", "state": "error", "error_type": type(exc).__name__}

        payload = {
            **result,
            **base_payload,
            "feature_snapshot": json_safe_feature_snapshot(features),
            "abc_rule_bundle_internal": abc_bundle,
        }
        if not dry_run:
            self.store.upsert_diagnosis(payload)
            if abc_bundle.get("evaluations"):
                self.store.persist_abc_evaluation(abc_bundle, source_snapshot_id=None)
                self.store.persist_abc_alerts(abc_bundle)
        return payload

    def backfill(self, start: datetime, end: datetime, dry_run: bool = False) -> list[dict[str, Any]]:
        step = int(self.diag_cfg["diagnosis_interval_minutes"])
        outputs = []
        run_id = None
        if not dry_run:
            self.store.ensure_schema()
            run_id = self.store.start_run("diagnosis_backfill", start, end)
        try:
            self.store.open_session()
            if self.diag_cfg.get("enforce_sync_barrier", True) and not self.store.local_csv_path:
                target, _ = self.latest_complete_target(end, wait=False)
                if target is not None:
                    end = min(end, target)
            for ts in iter_points(start, end, step):
                outputs.append(self.diagnose_point(ts, dry_run=dry_run))
            if run_id is not None:
                self.store.finish_run(run_id, "ok", rows_written=len(outputs), details={"dry_run": dry_run})
        except Exception as exc:
            if run_id is not None:
                self.store.finish_run(run_id, "error", rows_written=len(outputs), message=str(exc))
            raise
        finally:
            self.store.close_session()
        return outputs

    def startup_backfill(self, dry_run: bool = False) -> list[dict[str, Any]]:
        target, _ = self.latest_complete_target(wait=False)
        end = target or floor_to_interval(datetime.now(), int(self.diag_cfg["diagnosis_interval_minutes"]))
        start = end - timedelta(hours=float(self.diag_cfg["startup_backfill_hours"]))
        return self.backfill(start, end, dry_run=dry_run)

    def loop_forever(self) -> None:
        interval = int(self.diag_cfg["diagnosis_interval_minutes"])
        self.store.ensure_schema()
        self.startup_backfill(dry_run=False)
        while True:
            target, _ = self.latest_complete_target(wait=True)
            if target is not None:
                self.diagnose_point(target, dry_run=False)
            time.sleep(max(30, interval * 60))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("T", " ")).replace(second=0, microsecond=0)


def main() -> int:
    parser = argparse.ArgumentParser(description="V3 automatic diagnosis scheduler.")
    parser.add_argument("--config", default="")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--once", action="store_true", help="Run startup backfill once and exit.")
    parser.add_argument("--loop", action="store_true", help="Run startup backfill then keep diagnosing every interval.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    scheduler = AutoDiagnosisScheduler(args.config or None)
    if args.start or args.end:
        end = parse_time(args.end) if args.end else floor_to_interval(datetime.now(), int(scheduler.diag_cfg["diagnosis_interval_minutes"]))
        start = parse_time(args.start) if args.start else end - timedelta(hours=float(scheduler.diag_cfg["startup_backfill_hours"]))
        rows = scheduler.backfill(start, end, dry_run=args.dry_run)
    elif args.loop:
        scheduler.loop_forever()
        return 0
    else:
        rows = scheduler.startup_backfill(dry_run=args.dry_run)
    print(json.dumps({"ok": True, "count": len(rows), "dry_run": args.dry_run}, ensure_ascii=False, default=str, indent=2))
    if rows:
        print(json.dumps(rows[-1], ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
