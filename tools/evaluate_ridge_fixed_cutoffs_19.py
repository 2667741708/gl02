from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from run_chronos_sparse_prepredict import SPARSE_COVARIATES  # noqa: E402
from timeseries_model_contract import CONTEXT_MINUTES, HORIZON_MINUTES, SCHEMA, extract_feature_vector  # noqa: E402


TARGET_IDS = [
    "P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "Q_blast", "P_blast_cold", "P_blast", "T_blast", "T_top",
    "T_top_A", "T_top_B", "T_top_C", "T_top_D", "PI", "DP_total",
    "DP_upper", "DP_lower", "GasUtil",
]


METRIC_FIELDS = (
    "mae", "rmse", "iqr_nmae", "mase", "std_ratio", "diff_std_ratio",
    "direction_accuracy", "coverage_p10_p90", "pinball_p10", "pinball_p50",
    "pinball_p90", "wis_80", "mae_m00_30", "mae_m31_60", "mae_m61_120",
)


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return None if not math.isfinite(denominator) or abs(denominator) <= 1e-12 else float(numerator / denominator)


def pinball(truth: np.ndarray, prediction: np.ndarray, probability: float) -> float:
    error = truth - prediction
    return float(np.mean(np.maximum(probability * error, (probability - 1.0) * error)))


def clean_context(values: pd.Series) -> np.ndarray:
    series = pd.to_numeric(values, errors="coerce").interpolate(limit=5, limit_direction="forward").ffill(limit=15)
    if len(series) < CONTEXT_MINUTES or series.isna().any():
        raise ValueError("incomplete 480-minute context")
    return series.to_numpy(dtype=np.float32)


def baseline_interval(history: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    differences = np.diff(history)
    low = float(np.nanquantile(differences, 0.10))
    center = float(np.nanquantile(differences, 0.50))
    high = float(np.nanquantile(differences, 0.90))
    scale = np.sqrt(np.arange(1, horizon + 1, dtype=float))
    p50 = np.full(horizon, history[-1], dtype=float)
    return p50 + (low - center) * scale, p50, p50 + (high - center) * scale


def evaluate_window(
    history: np.ndarray,
    truth: np.ndarray,
    p10: np.ndarray,
    p50: np.ndarray,
    p90: np.ndarray,
    iqr: float,
) -> dict[str, Any]:
    valid = np.isfinite(truth) & np.isfinite(p10) & np.isfinite(p50) & np.isfinite(p90)
    horizon = len(truth)
    if valid.sum() < max(1, horizon // 2):
        return {"failed": True, "truth_points": int(valid.sum())}
    t, lo, mid, hi = truth[valid], p10[valid], p50[valid], p90[valid]
    error = mid - t
    absolute_error = np.abs(error)
    scale = max(float(iqr), abs(float(np.nanmedian(history))) * 0.01, 1e-6)
    history_finite = history[np.isfinite(history)]
    naive_scale = float(np.mean(np.abs(np.diff(history_finite)))) if len(history_finite) > 1 else float("nan")
    truth_diff = np.diff(np.r_[history_finite[-1], t])
    prediction_diff = np.diff(np.r_[history_finite[-1], mid])
    alpha = 0.20
    interval_score = (hi - lo) + (2.0 / alpha) * np.maximum(lo - t, 0.0) + (2.0 / alpha) * np.maximum(t - hi, 0.0)
    wis = (0.5 * np.abs(t - mid) + (alpha / 2.0) * interval_score) / (0.5 + alpha / 2.0)
    result: dict[str, Any] = {
        "failed": False,
        "truth_points": int(valid.sum()),
        "missing_ratio": float(1.0 - valid.mean()),
        "mae": float(absolute_error.mean()),
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "iqr_nmae": float(absolute_error.mean() / scale),
        "mase": safe_ratio(float(absolute_error.mean()), naive_scale),
        "std_ratio": safe_ratio(float(np.std(mid)), float(np.std(t))),
        "diff_std_ratio": safe_ratio(float(np.std(prediction_diff)), float(np.std(truth_diff))),
        "direction_accuracy": float(np.mean(np.sign(prediction_diff) == np.sign(truth_diff))),
        "coverage_p10_p90": float(np.mean((t >= lo) & (t <= hi))),
        "pinball_p10": pinball(t, lo, 0.10),
        "pinball_p50": pinball(t, mid, 0.50),
        "pinball_p90": pinball(t, hi, 0.90),
        "wis_80": float(np.mean(wis)),
    }
    for label, start, end in (("m00_30", 0, 30), ("m31_60", 30, 60), ("m61_120", 60, 120)):
        subset = absolute_error[start:min(end, len(absolute_error))]
        result[f"mae_{label}"] = None if not len(subset) else float(subset.mean())
    return result


def aggregate_5min(values: np.ndarray) -> np.ndarray:
    if len(values) != HORIZON_MINUTES:
        raise ValueError(f"5-minute aggregation requires {HORIZON_MINUTES} points, got {len(values)}")
    return np.nanmean(values.reshape(-1, 5), axis=1)


def load_model(model_dir: Path, target_id: str, variant: str) -> dict[str, Any]:
    path = model_dir / f"ridge_delta__{target_id}__{variant}.json"
    model = json.loads(path.read_text(encoding="utf-8"))
    if model.get("schema") != SCHEMA:
        raise ValueError(f"unsupported model schema in {path.name}: {model.get('schema')}")
    return model


def predict_ridge(model: dict[str, Any], target_values: np.ndarray, covariates: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    covariate_ids = list(model.get("covariate_ids") or [])
    names, features = extract_feature_vector(target_values.tolist(), {key: value.tolist() for key, value in covariates.items()}, covariate_ids)
    if names != model.get("feature_names"):
        raise ValueError("runtime feature names do not match trained model")
    x = np.asarray(features, dtype=float)
    center = np.asarray(model["x_center"], dtype=float)
    scale = np.asarray(model["x_scale"], dtype=float)
    coefficient = np.asarray(model["coefficient"], dtype=float)
    y_center = np.asarray(model["y_center"], dtype=float)
    delta = y_center + ((x - center) / scale) @ coefficient
    p50 = float(target_values[-1]) + delta
    p10 = p50 + np.asarray(model["residual_q10"], dtype=float)
    p90 = p50 + np.asarray(model["residual_q90"], dtype=float)
    return p10, p50, p90


def metric_row(
    model_name: str,
    target_id: str,
    variant: str,
    cutoff: pd.Timestamp,
    history: np.ndarray,
    truth: np.ndarray,
    forecasts: tuple[np.ndarray, np.ndarray, np.ndarray],
    iqr: float,
    latency_ms: float,
    model_bytes: int,
    aggregation: str,
) -> dict[str, Any]:
    p10, p50, p90 = forecasts
    if aggregation == "5min_mean":
        truth = aggregate_5min(truth)
        p10 = aggregate_5min(p10)
        p50 = aggregate_5min(p50)
        p90 = aggregate_5min(p90)
        history = np.asarray([float(history[-1])], dtype=float)
    metrics = evaluate_window(history, truth, p10, p50, p90, iqr)
    metrics.setdefault("missing_ratio", 0.0)
    for field in METRIC_FIELDS:
        metrics.setdefault(field, None)
    return {
        "model": model_name,
        "target_id": target_id,
        "variant": variant,
        "aggregation": aggregation,
        "cutoff": cutoff.isoformat(sep=" "),
        "latency_ms": latency_ms,
        "train_seconds": 0.0,
        "model_bytes": model_bytes,
        "peak_ram_mb": 0.0,
        "peak_gpu_mb": 0.0,
        **metrics,
    }


def summarize(detail: pd.DataFrame) -> list[dict[str, Any]]:
    metrics = [
        "mae", "rmse", "iqr_nmae", "mase", "std_ratio", "diff_std_ratio",
        "direction_accuracy", "coverage_p10_p90", "pinball_p10", "pinball_p50",
        "pinball_p90", "wis_80", "mae_m00_30", "mae_m31_60", "mae_m61_120",
        "latency_ms", "peak_ram_mb", "peak_gpu_mb", "model_bytes",
    ]
    rows = []
    for (model_name, target_id, variant), group in detail.groupby(["model", "target_id", "variant"], sort=False):
        row: dict[str, Any] = {
            "model": model_name,
            "target_id": target_id,
            "variant": variant,
            "windows": int(len(group)),
            "failed_windows": int(group["failed"].sum()),
            "truth_points": int(group["truth_points"].sum()),
            "missing_ratio": float(group["missing_ratio"].mean()),
            "train_seconds": 0.0,
        }
        for field in metrics:
            values = pd.to_numeric(group[field], errors="coerce").dropna()
            row[field] = None if values.empty else float(values.mean())
        rows.append(row)
    return rows


def read_cutoffs(path: Path) -> list[pd.Timestamp]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [pd.Timestamp(item).tz_localize(None) for item in data["cutoffs"]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate trained Ridge-Delta models on fixed Chronos/TTM cutoffs.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--cutoff-summary", required=True)
    parser.add_argument("--model-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "models"))
    parser.add_argument("--output-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "results"))
    args = parser.parse_args()

    frame = pd.read_csv(args.input_csv, index_col="ts", parse_dates=["ts"])
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame = frame.reindex(pd.date_range(frame.index.min().floor("min"), frame.index.max().floor("min"), freq="1min"))
    cutoffs = read_cutoffs(Path(args.cutoff_summary))
    model_dir = Path(args.model_dir)
    detail_rows: list[dict[str, Any]] = []

    for cutoff in cutoffs:
        print(f"CUTOFF {cutoff}", flush=True)
        for target_id in TARGET_IDS:
            context = frame[target_id].loc[(frame.index > cutoff - pd.Timedelta(minutes=CONTEXT_MINUTES)) & (frame.index <= cutoff)]
            truth = pd.to_numeric(frame[target_id].loc[(frame.index > cutoff) & (frame.index <= cutoff + pd.Timedelta(minutes=HORIZON_MINUTES))], errors="coerce").to_numpy(dtype=float)
            history = clean_context(context)
            history_values = frame[target_id].loc[frame.index <= cutoff].tail(30 * 24 * 60).to_numpy(dtype=float)
            q1, q3 = np.nanquantile(history_values, [0.25, 0.75])
            iqr = float(q3 - q1)
            baseline = baseline_interval(history, HORIZON_MINUTES)
            for aggregation in ("1min", "5min_mean"):
                detail_rows.append(metric_row("last_value", target_id, "target_only", cutoff, history, truth, baseline, iqr, 0.02, 0, aggregation))

            for variant in ("target_only", "expert_sparse"):
                model = load_model(model_dir, target_id, variant)
                covariate_ids = [] if variant == "target_only" else [item for item in SPARSE_COVARIATES[target_id] if item in frame]
                covariates = {}
                for covariate_id in covariate_ids:
                    cov_context = frame[covariate_id].loc[(frame.index > cutoff - pd.Timedelta(minutes=CONTEXT_MINUTES)) & (frame.index <= cutoff)]
                    covariates[covariate_id] = clean_context(cov_context)
                started = time.perf_counter()
                forecasts = predict_ridge(model, history, covariates)
                latency_ms = (time.perf_counter() - started) * 1000.0
                model_bytes = (model_dir / f"ridge_delta__{target_id}__{variant}.json").stat().st_size
                for aggregation in ("1min", "5min_mean"):
                    detail_rows.append(metric_row("ridge_delta", target_id, variant, cutoff, history, truth, forecasts, iqr, latency_ms, model_bytes, aggregation))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail = pd.DataFrame(detail_rows)
    detail_path = output_dir / f"ridge_fixed_cutoff_detail_{stamp}.csv"
    summary_path = output_dir / f"ridge_fixed_cutoff_summary_{stamp}.json"
    report_path = output_dir / f"ridge_fixed_cutoff_report_{stamp}.md"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")

    summary_rows = []
    for aggregation, group in detail.groupby("aggregation", sort=False):
        rows = summarize(group.drop(columns=["aggregation"]))
        for row in rows:
            row["aggregation"] = aggregation
        summary_rows.extend(rows)

    summary = {
        "requirement": "REQ-TS-FORECAST-MULTI-MODEL-BENCHMARK-20260808",
        "created_at": datetime.now().isoformat(sep=" "),
        "context_minutes": CONTEXT_MINUTES,
        "prediction_minutes": HORIZON_MINUTES,
        "cutoffs": [item.isoformat(sep=" ") for item in cutoffs],
        "aggregation_modes": ["1min", "5min_mean"],
        "summary_by_model_target": summary_rows,
        "detail_csv": str(detail_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report = [
        "# Ridge-Delta同切点与5分钟聚合回测",
        "",
        f"- 生成时间：{summary['created_at']}",
        f"- 同切点数量：{len(cutoffs)}",
        "- 聚合口径：1分钟原始真值、5分钟均值真值",
        "",
        "|聚合|模型|输入|变量|IQR-NMAE|STD比|差分STD比|方向准确率|80%覆盖率|WIS|",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary_rows:
        def show(field: str) -> str:
            value = item.get(field)
            return "-" if value is None else f"{value:.4f}"
        report.append(
            f"|{item['aggregation']}|{item['model']}|{item['variant']}|{item['target_id']}|"
            f"{show('iqr_nmae')}|{show('std_ratio')}|{show('diff_std_ratio')}|"
            f"{show('direction_accuracy')}|{show('coverage_p10_p90')}|{show('wis_80')}|"
        )
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("DETAIL", detail_path, flush=True)
    print("SUMMARY", summary_path, flush=True)
    print("REPORT", report_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
