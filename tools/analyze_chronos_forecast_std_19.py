from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from select_and_backtest_chronos_main_variables_19 import load_core_frame


ROOT = Path(__file__).resolve().parents[1]
FEATURE_VARIANTS = {
    "iqr_backtest_current": "current",
    "iqr_backtest_target_only": "target_only",
    "iqr_backtest_sparse": "sparse",
}


def finite_std(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    return float(np.std(finite, ddof=1)) if len(finite) >= 2 else float("nan")


def finite_amplitude(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    return float(np.quantile(finite, 0.95) - np.quantile(finite, 0.05)) if len(finite) >= 2 else float("nan")


def ratio(numerator: float, denominator: float) -> float:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator <= 1e-12:
        return float("nan")
    return numerator / denominator


def weighted_average(group: pd.DataFrame, column: str) -> float:
    valid = pd.to_numeric(group[column], errors="coerce").notna()
    if not valid.any():
        return float("nan")
    values = pd.to_numeric(group.loc[valid, column], errors="coerce").to_numpy(dtype=float)
    weights = pd.to_numeric(group.loc[valid, "points"], errors="coerce").to_numpy(dtype=float)
    return float(np.average(values, weights=weights))


def dispersion_class(std_ratio_actual: float, diff_std_ratio_actual: float) -> str:
    if std_ratio_actual < 0.25 or diff_std_ratio_actual < 0.10:
        return "严重欠离散"
    if std_ratio_actual < 0.50 or diff_std_ratio_actual < 0.25:
        return "欠离散"
    if std_ratio_actual < 0.75 or diff_std_ratio_actual < 0.50:
        return "偏平滑"
    return "接近真实波动"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Chronos p50 dispersion with actual 19-target curves.")
    parser.add_argument(
        "--raw-json",
        default=str(ROOT / "logs" / "chronos_iqr_mae_19" / "chronos_iqr_mae_raw_20260808_022144.json"),
    )
    parser.add_argument("--db-host", default="10.30.220.12")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="bf_trend")
    parser.add_argument("--db-user", default="gl02_reader")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument("--history-minutes", type=int, default=480)
    parser.add_argument("--output-dir", default=str(ROOT / "logs" / "chronos_forecast_std_19"))
    args = parser.parse_args()

    raw_results = json.loads(Path(args.raw_json).read_text(encoding="utf-8"))
    predictions = []
    for batch in raw_results:
        for prediction in (batch.get("result") or {}).get("predictions") or []:
            if prediction.get("feature_type") in FEATURE_VARIANTS:
                predictions.append(prediction)
    if not predictions:
        raise SystemExit("no supported predictions were found")

    cutoffs = [pd.Timestamp(item["cutoff_time"]) for item in predictions]
    future_times = [
        pd.Timestamp(timestamp)
        for prediction in predictions
        for timestamp in prediction.get("future_timestamps") or []
    ]
    start = min(cutoffs).to_pydatetime() - timedelta(minutes=args.history_minutes + 10)
    end = max(future_times).to_pydatetime() + timedelta(minutes=1)
    password = os.environ.get(args.db_password_env, "")
    if not password:
        raise SystemExit(f"missing database password environment variable: {args.db_password_env}")
    conn_params: dict[str, Any] = {
        "host": args.db_host,
        "port": args.db_port,
        "dbname": args.db_name,
        "user": args.db_user,
        "password": password,
        "connect_timeout": 12,
    }
    truth_frame = load_core_frame(conn_params, start, end)
    if truth_frame.empty:
        raise SystemExit("no actual history was loaded")

    rows = []
    for prediction in predictions:
        target_id = str(prediction.get("target_id"))
        variant = FEATURE_VARIANTS[str(prediction.get("feature_type"))]
        if target_id not in truth_frame:
            continue
        cutoff = pd.Timestamp(prediction["cutoff_time"])
        timestamps = pd.to_datetime(prediction.get("future_timestamps") or [])
        p50 = pd.to_numeric(pd.Series(prediction.get("p50") or []), errors="coerce").to_numpy(dtype=float)
        p10 = pd.to_numeric(pd.Series(prediction.get("p10") or []), errors="coerce").to_numpy(dtype=float)
        p90 = pd.to_numeric(pd.Series(prediction.get("p90") or []), errors="coerce").to_numpy(dtype=float)
        actual_series = pd.to_numeric(truth_frame[target_id].reindex(timestamps), errors="coerce")
        actual = actual_series.to_numpy(dtype=float)
        history_series = pd.to_numeric(
            truth_frame.loc[
                (truth_frame.index > cutoff - pd.Timedelta(minutes=args.history_minutes))
                & (truth_frame.index <= cutoff),
                target_id,
            ],
            errors="coerce",
        )
        history = history_series.to_numpy(dtype=float)

        valid = np.isfinite(p50) & np.isfinite(actual)
        if valid.sum() < 30:
            continue
        forecast_valid = p50[valid]
        actual_valid = actual[valid]
        p10_valid = p10[valid]
        p90_valid = p90[valid]
        forecast_std = finite_std(forecast_valid)
        actual_std = finite_std(actual_valid)
        history_std = finite_std(history)
        forecast_diff_std = finite_std(np.diff(forecast_valid))
        actual_diff_std = finite_std(actual_series.diff().to_numpy(dtype=float))
        history_diff_std = finite_std(history_series.diff().to_numpy(dtype=float))
        interval_valid = np.isfinite(p10_valid) & np.isfinite(p90_valid)
        coverage = float(
            np.mean((actual_valid[interval_valid] >= p10_valid[interval_valid]) & (actual_valid[interval_valid] <= p90_valid[interval_valid]))
        ) if interval_valid.any() else float("nan")
        mean_interval_width = float(np.mean(p90_valid[interval_valid] - p10_valid[interval_valid])) if interval_valid.any() else float("nan")

        rows.append(
            {
                "cutoff": cutoff.isoformat(sep=" "),
                "target_id": target_id,
                "variant": variant,
                "points": int(valid.sum()),
                "forecast_std": forecast_std,
                "actual_std": actual_std,
                "history_8h_std": history_std,
                "std_ratio_actual": ratio(forecast_std, actual_std),
                "std_ratio_history": ratio(forecast_std, history_std),
                "forecast_diff_std": forecast_diff_std,
                "actual_diff_std": actual_diff_std,
                "history_diff_std": history_diff_std,
                "diff_std_ratio_actual": ratio(forecast_diff_std, actual_diff_std),
                "diff_std_ratio_history": ratio(forecast_diff_std, history_diff_std),
                "forecast_amplitude_p95_p05": finite_amplitude(forecast_valid),
                "actual_amplitude_p95_p05": finite_amplitude(actual_valid),
                "amplitude_ratio_actual": ratio(finite_amplitude(forecast_valid), finite_amplitude(actual_valid)),
                "p10_p90_coverage": coverage,
                "mean_p10_p90_width": mean_interval_width,
            }
        )

    detail = pd.DataFrame(rows)
    if detail.empty:
        raise SystemExit("no prediction could be compared with actual values")
    summary_rows = []
    for (target_id, variant), group in detail.groupby(["target_id", "variant"], sort=False):
        std_ratio_actual = weighted_average(group, "std_ratio_actual")
        diff_ratio_actual = weighted_average(group, "diff_std_ratio_actual")
        summary_rows.append(
            {
                "target_id": target_id,
                "variant": variant,
                "cutoffs": int(group["cutoff"].nunique()),
                "points": int(group["points"].sum()),
                "forecast_std": weighted_average(group, "forecast_std"),
                "actual_std": weighted_average(group, "actual_std"),
                "history_8h_std": weighted_average(group, "history_8h_std"),
                "std_ratio_actual": std_ratio_actual,
                "std_ratio_history": weighted_average(group, "std_ratio_history"),
                "forecast_diff_std": weighted_average(group, "forecast_diff_std"),
                "actual_diff_std": weighted_average(group, "actual_diff_std"),
                "diff_std_ratio_actual": diff_ratio_actual,
                "amplitude_ratio_actual": weighted_average(group, "amplitude_ratio_actual"),
                "p10_p90_coverage": weighted_average(group, "p10_p90_coverage"),
                "mean_p10_p90_width": weighted_average(group, "mean_p10_p90_width"),
                "dispersion_class": dispersion_class(std_ratio_actual, diff_ratio_actual),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values(["variant", "std_ratio_actual"])
    current = summary.loc[summary["variant"] == "current"].sort_values("std_ratio_actual")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail_path = output_dir / f"chronos_forecast_std_detail_{stamp}.csv"
    summary_path = output_dir / f"chronos_forecast_std_summary_{stamp}.csv"
    current_path = output_dir / f"chronos_forecast_std_current_{stamp}.csv"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    current.to_csv(current_path, index=False, encoding="utf-8-sig")
    print("DETAIL", detail_path, flush=True)
    print("SUMMARY", summary_path, flush=True)
    print("CURRENT", current_path, flush=True)
    for row in current.itertuples(index=False):
        print(
            "STD",
            row.target_id,
            "forecast_actual",
            [round(row.forecast_std, 6), round(row.actual_std, 6)],
            "ratio",
            round(row.std_ratio_actual, 4),
            "diff_ratio",
            round(row.diff_std_ratio_actual, 4),
            "coverage",
            round(row.p10_p90_coverage, 4),
            "class",
            row.dispersion_class,
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
