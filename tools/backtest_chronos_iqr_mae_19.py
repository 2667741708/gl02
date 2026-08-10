from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_DIR = ROOT / "自动诊断服务"
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

from local_pg_ws_bridge import build_chronos_job, clean_feature_series, fetch_chronos_feature_frame  # noqa: E402
from backtest_chronos2_from_pg import post_json  # noqa: E402
from run_chronos_sparse_prepredict import SPARSE_COVARIATES  # noqa: E402


TARGET_IDS = list(SPARSE_COVARIATES)
RAW_TARGET_IDS = [target_id for target_id in TARGET_IDS if target_id != "T_top"]
VARIANT_FEATURE_TYPES = {
    "current": "iqr_backtest_current",
    "target_only": "iqr_backtest_target_only",
    "sparse": "iqr_backtest_sparse",
}
FEATURE_TYPE_VARIANTS = {value: key for key, value in VARIANT_FEATURE_TYPES.items()}


def load_target_history(conn_params: dict[str, Any], start: datetime, end: datetime) -> pd.DataFrame:
    query = """
        SELECT r.variable_name, v.ts, v.value
        FROM bf_sensor.sensor_registry AS r
        JOIN bf_sensor.one_minute_values AS v ON v.tag_long_name = r.tag_long_name
        WHERE r.variable_name = ANY(%s)
          AND v.ts >= %s
          AND v.ts <= %s
        ORDER BY v.ts, r.variable_name
    """
    with psycopg.connect(**conn_params) as conn:
        rows = conn.execute(query, (RAW_TARGET_IDS, start, end)).fetchall()
    frame = pd.DataFrame(rows, columns=["variable_name", "ts", "value"])
    if frame.empty:
        return pd.DataFrame()
    pivot = frame.pivot_table(index="ts", columns="variable_name", values="value", aggfunc="last").sort_index()
    pivot.index = pd.to_datetime(pivot.index).tz_localize(None)
    top_columns = [column for column in ("T_top_A", "T_top_B", "T_top_C", "T_top_D") if column in pivot]
    pivot["T_top"] = pivot[top_columns].mean(axis=1)
    return pivot


def sparse_covariates(history: pd.DataFrame, target_id: str, context_minutes: int) -> list[dict[str, Any]]:
    context = history.tail(context_minutes)
    result = []
    for covariate_id in SPARSE_COVARIATES[target_id]:
        if covariate_id not in context.columns:
            continue
        values = clean_feature_series(context[covariate_id], context_minutes)
        result.append(
            {
                "id": covariate_id,
                "name": covariate_id,
                "values": values,
                "nonnull_count": sum(value is not None for value in values),
            }
        )
    return result


def build_variant_job(
    frame: pd.DataFrame,
    target_id: str,
    cutoff: pd.Timestamp,
    variant: str,
    context_minutes: int,
    horizon_minutes: int,
) -> dict[str, Any]:
    history = frame.loc[frame.index <= cutoff]
    job = build_chronos_job(history, target_id, horizon_minutes, context_minutes)
    if variant == "target_only":
        job["covariates"] = []
        job["covariate_ids"] = []
    elif variant == "sparse":
        job["covariates"] = sparse_covariates(history, target_id, context_minutes)
        job["covariate_ids"] = [item["id"] for item in job["covariates"]]
    job["feature_type"] = VARIANT_FEATURE_TYPES[variant]
    job["feature_engine"] = "BACKTEST-CHRONOS-19-IQR-MAE-20260808"
    job["cutoff_time"] = cutoff.isoformat(sep=" ")
    job["future_timestamps"] = [
        (cutoff + pd.Timedelta(minutes=minute)).isoformat(sep=" ")
        for minute in range(1, horizon_minutes + 1)
    ]
    return job


def mae(prediction: np.ndarray, truth: np.ndarray) -> float:
    return float(np.mean(np.abs(prediction - truth)))


def accuracy_class(iqr_nmae: float) -> str:
    if iqr_nmae <= 0.25:
        return "高"
    if iqr_nmae <= 0.50:
        return "较高"
    if iqr_nmae <= 1.00:
        return "一般"
    return "较低"


def evaluate_prediction(
    prediction: dict[str, Any],
    target_history: pd.DataFrame,
    cutoff: pd.Timestamp,
    baseline_days: int,
) -> dict[str, Any] | None:
    target_id = str(prediction.get("target_id"))
    variant = FEATURE_TYPE_VARIANTS.get(str(prediction.get("feature_type")))
    if not variant or target_id not in target_history:
        return None

    timestamps = pd.to_datetime(prediction.get("future_timestamps") or [])
    forecast = pd.to_numeric(pd.Series(prediction.get("p50") or []), errors="coerce").to_numpy(dtype=float)
    truth = pd.to_numeric(target_history[target_id].reindex(timestamps), errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(forecast) & np.isfinite(truth)
    if not valid.any():
        return None
    forecast = forecast[valid]
    truth = truth[valid]

    baseline = pd.to_numeric(
        target_history.loc[
            (target_history.index > cutoff - pd.Timedelta(days=baseline_days))
            & (target_history.index <= cutoff),
            target_id,
        ],
        errors="coerce",
    ).dropna()
    if baseline.empty:
        return None
    q1 = float(baseline.quantile(0.25))
    q2 = float(baseline.quantile(0.50))
    q3 = float(baseline.quantile(0.75))
    iqr = q3 - q1
    scale_floor = max(abs(q2) * 0.01, 1e-6)
    scale = max(iqr, scale_floor)
    used_scale_floor = iqr < scale_floor

    raw_mae = mae(forecast, truth)
    median_mae = mae(np.full_like(truth, q2), truth)
    last_value = float(baseline.iloc[-1])
    persistence_mae = mae(np.full_like(truth, last_value), truth)
    return {
        "cutoff": cutoff.isoformat(sep=" "),
        "target_id": target_id,
        "variant": variant,
        "points": int(valid.sum()),
        "covariate_count": int(prediction.get("covariate_count") or 0),
        "q1": q1,
        "normal_median": q2,
        "q3": q3,
        "iqr": iqr,
        "normalization_scale": scale,
        "used_scale_floor": used_scale_floor,
        "mae": raw_mae,
        "iqr_nmae": raw_mae / scale,
        "median_baseline_mae": median_mae,
        "median_baseline_iqr_nmae": median_mae / scale,
        "persistence_mae": persistence_mae,
        "persistence_iqr_nmae": persistence_mae / scale,
        "skill_vs_median": None if median_mae <= 1e-12 else 1.0 - raw_mae / median_mae,
        "skill_vs_persistence": None if persistence_mae <= 1e-12 else 1.0 - raw_mae / persistence_mae,
    }


def summarize(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (target_id, variant), group in detail.groupby(["target_id", "variant"], sort=False):
        weights = group["points"].to_numpy(dtype=float)
        weighted = lambda column: float(np.average(group[column].to_numpy(dtype=float), weights=weights))
        iqr_nmae = weighted("iqr_nmae")
        rows.append(
            {
                "target_id": target_id,
                "variant": variant,
                "cutoffs": int(group["cutoff"].nunique()),
                "points": int(group["points"].sum()),
                "covariate_count": weighted("covariate_count"),
                "mae": weighted("mae"),
                "iqr_nmae": iqr_nmae,
                "accuracy_class": accuracy_class(iqr_nmae),
                "median_baseline_iqr_nmae": weighted("median_baseline_iqr_nmae"),
                "persistence_iqr_nmae": weighted("persistence_iqr_nmae"),
                "skill_vs_median": weighted("skill_vs_median"),
                "skill_vs_persistence": weighted("skill_vs_persistence"),
                "q1": weighted("q1"),
                "normal_median": weighted("normal_median"),
                "q3": weighted("q3"),
                "iqr": weighted("iqr"),
            }
        )
    return pd.DataFrame(rows).sort_values(["target_id", "iqr_nmae"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest 19 Chronos targets using raw MAE and 30-day IQR-normalized MAE.")
    parser.add_argument("--db-host", default="10.30.220.12")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="bf_trend")
    parser.add_argument("--db-user", default="gl02_reader")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument("--chronos-url", default="http://10.30.220.12:8777")
    parser.add_argument("--baseline-days", type=int, default=30)
    parser.add_argument("--context-minutes", type=int, default=480)
    parser.add_argument("--horizon-minutes", type=int, default=120)
    parser.add_argument("--cutoff-offset-hours", default="0,12")
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument("--output-dir", default=str(ROOT / "logs" / "chronos_iqr_mae_19"))
    args = parser.parse_args()

    password = os.environ.get(args.db_password_env, "")
    if not password:
        raise SystemExit(f"missing database password environment variable: {args.db_password_env}")
    conn_params = {
        "host": args.db_host,
        "port": args.db_port,
        "dbname": args.db_name,
        "user": args.db_user,
        "password": password,
        "connect_timeout": 12,
    }

    with psycopg.connect(**conn_params, row_factory=dict_row) as conn:
        model_frame = fetch_chronos_feature_frame(conn, datetime.now() - timedelta(days=3))
    if model_frame.empty:
        raise SystemExit("no model feature data was loaded")
    model_frame.index = pd.to_datetime(model_frame.index).tz_localize(None)
    latest = model_frame.index.max().floor("min")
    offsets = [float(item.strip()) for item in args.cutoff_offset_hours.split(",") if item.strip()]
    cutoffs = [
        latest - pd.Timedelta(minutes=args.horizon_minutes) - pd.Timedelta(hours=offset)
        for offset in offsets
    ]

    history_start = min(cutoffs).to_pydatetime() - timedelta(days=args.baseline_days, minutes=10)
    target_history = load_target_history(conn_params, history_start, latest.to_pydatetime())
    if target_history.empty:
        raise SystemExit("no target history was loaded")

    detail_rows = []
    raw_results = []
    variants = list(VARIANT_FEATURE_TYPES)
    for cutoff in cutoffs:
        jobs = [
            build_variant_job(model_frame, target_id, cutoff, variant, args.context_minutes, args.horizon_minutes)
            for variant in variants
            for target_id in TARGET_IDS
        ]
        payload = {
            "jobs": jobs,
            "feature_source": {
                "type": "postgresql_iqr_mae_backtest",
                "time_start": model_frame.index.min().isoformat(sep=" "),
                "time_end": model_frame.index.max().isoformat(sep=" "),
            },
            "request": {
                "cutoff_time": cutoff.isoformat(sep=" "),
                "target_ids": TARGET_IDS,
                "variants": variants,
                "baseline_days": args.baseline_days,
                "context_minutes": args.context_minutes,
                "prediction_minutes": args.horizon_minutes,
            },
        }
        print(f"REQUEST cutoff={cutoff} jobs={len(jobs)} variants={variants}", flush=True)
        result = post_json(args.chronos_url, payload, args.timeout_seconds)
        raw_results.append({"cutoff": cutoff.isoformat(sep=" "), "result": result})
        for prediction in result.get("predictions") or []:
            row = evaluate_prediction(prediction, target_history, cutoff, args.baseline_days)
            if row:
                detail_rows.append(row)
        print(f"RESULT cutoff={cutoff} predictions={len(result.get('predictions') or [])}", flush=True)

    detail = pd.DataFrame(detail_rows)
    if detail.empty:
        raise SystemExit("no predictions could be scored")
    summary = summarize(detail)
    winners = summary.loc[summary.groupby("target_id")["iqr_nmae"].idxmin()].sort_values("iqr_nmae")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail_path = output_dir / f"chronos_iqr_mae_detail_{stamp}.csv"
    summary_path = output_dir / f"chronos_iqr_mae_summary_{stamp}.csv"
    winners_path = output_dir / f"chronos_iqr_mae_winners_{stamp}.csv"
    raw_path = output_dir / f"chronos_iqr_mae_raw_{stamp}.json"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    winners.to_csv(winners_path, index=False, encoding="utf-8-sig")
    raw_path.write_text(json.dumps(raw_results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("DETAIL", detail_path, flush=True)
    print("SUMMARY", summary_path, flush=True)
    print("WINNERS", winners_path, flush=True)
    for row in winners.itertuples(index=False):
        print(
            "BEST",
            row.target_id,
            row.variant,
            "mae",
            round(row.mae, 6),
            "iqr_nmae",
            round(row.iqr_nmae, 4),
            "class",
            row.accuracy_class,
            "skill_vs_persistence",
            round(row.skill_vs_persistence, 4) if math.isfinite(row.skill_vs_persistence) else None,
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
