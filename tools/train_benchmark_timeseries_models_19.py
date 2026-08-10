from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd

from run_chronos_sparse_prepredict import SPARSE_COVARIATES
from select_and_backtest_chronos_main_variables_19 import TARGET_IDS, load_core_frame
from timeseries_model_contract import CONTEXT_MINUTES, HORIZON_MINUTES, SCHEMA, extract_feature_vector


ROOT = Path(__file__).resolve().parents[1]


def finite(values: list[Any]) -> np.ndarray:
    output = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    return output


def sample_at(frame: pd.DataFrame, index: int, target_id: str, covariate_ids: list[str]) -> tuple[list[str], list[float], np.ndarray, np.ndarray]:
    context = frame.iloc[index - CONTEXT_MINUTES + 1:index + 1]
    truth = frame[target_id].iloc[index + 1:index + 1 + HORIZON_MINUTES].to_numpy(dtype=float)
    target_values = context[target_id].tolist()
    covariates = {item: context[item].tolist() for item in covariate_ids}
    names, features = extract_feature_vector(target_values, covariates, covariate_ids)
    history = np.asarray(target_values, dtype=float)
    return names, features, truth, history


def fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x_center = np.median(x, axis=0)
    x_scale = np.quantile(x, 0.75, axis=0) - np.quantile(x, 0.25, axis=0)
    std = np.std(x, axis=0)
    x_scale = np.where(x_scale > 1e-9, x_scale, np.where(std > 1e-9, std, 1.0))
    xs = (x - x_center) / x_scale
    y_center = np.median(y, axis=0)
    yc = y - y_center
    matrix = xs.T @ xs + np.eye(xs.shape[1]) * alpha
    try:
        coefficient = np.linalg.solve(matrix, xs.T @ yc)
    except np.linalg.LinAlgError:
        coefficient = np.linalg.pinv(matrix) @ xs.T @ yc
    return x_center, x_scale, y_center, coefficient


def predict_matrix(x: np.ndarray, x_center: np.ndarray, x_scale: np.ndarray, y_center: np.ndarray, coefficient: np.ndarray) -> np.ndarray:
    return y_center + ((x - x_center) / x_scale) @ coefficient


def pinball(truth: np.ndarray, prediction: np.ndarray, quantile: float) -> float:
    error = truth - prediction
    return float(np.mean(np.maximum(quantile * error, (quantile - 1.0) * error)))


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return None if not math.isfinite(denominator) or abs(denominator) <= 1e-12 else float(numerator / denominator)


def evaluate_window(history: np.ndarray, truth: np.ndarray, p10: np.ndarray, p50: np.ndarray, p90: np.ndarray, iqr: float) -> dict[str, Any]:
    valid = np.isfinite(truth) & np.isfinite(p10) & np.isfinite(p50) & np.isfinite(p90)
    if valid.sum() < HORIZON_MINUTES // 2:
        return {"failed": True, "truth_points": int(valid.sum())}
    t = truth[valid]
    lo = p10[valid]
    mid = p50[valid]
    hi = p90[valid]
    error = mid - t
    abs_error = np.abs(error)
    scale = max(float(iqr), abs(float(np.median(history))) * 0.01, 1e-6)
    naive_scale = float(np.mean(np.abs(np.diff(history[np.isfinite(history)]))))
    truth_path = np.r_[history[-1], t]
    pred_path = np.r_[history[-1], mid]
    truth_diff = np.diff(truth_path)
    pred_diff = np.diff(pred_path)
    alpha = 0.20
    interval_score = (hi - lo) + (2.0 / alpha) * np.maximum(lo - t, 0.0) + (2.0 / alpha) * np.maximum(t - hi, 0.0)
    wis = (0.5 * np.abs(t - mid) + (alpha / 2.0) * interval_score) / (0.5 + alpha / 2.0)
    result: dict[str, Any] = {
        "failed": False,
        "truth_points": int(valid.sum()),
        "missing_ratio": float(1.0 - valid.mean()),
        "mae": float(abs_error.mean()),
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "iqr_nmae": float(abs_error.mean() / scale),
        "mase": safe_ratio(float(abs_error.mean()), naive_scale),
        "std_ratio": safe_ratio(float(np.std(mid)), float(np.std(t))),
        "diff_std_ratio": safe_ratio(float(np.std(pred_diff)), float(np.std(truth_diff))),
        "direction_accuracy": float(np.mean(np.sign(pred_diff) == np.sign(truth_diff))),
        "coverage_p10_p90": float(np.mean((t >= lo) & (t <= hi))),
        "pinball_p10": pinball(t, lo, 0.10),
        "pinball_p50": pinball(t, mid, 0.50),
        "pinball_p90": pinball(t, hi, 0.90),
        "wis_80": float(np.mean(wis)),
    }
    for label, start, end in (("m00_30", 0, 30), ("m31_60", 30, 60), ("m61_120", 60, 120)):
        subset = abs_error[start:min(end, len(abs_error))]
        result[f"mae_{label}"] = None if not len(subset) else float(subset.mean())
    return result


def aggregate(detail: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    metric_columns = [
        "mae", "rmse", "iqr_nmae", "mase", "std_ratio", "diff_std_ratio",
        "direction_accuracy", "coverage_p10_p90", "pinball_p10", "pinball_p50",
        "pinball_p90", "wis_80", "mae_m00_30", "mae_m31_60", "mae_m61_120", "latency_ms",
    ]
    for (target_id, variant), group in detail.groupby(["target_id", "variant"], sort=False):
        row: dict[str, Any] = {
            "model": "ridge_delta",
            "target_id": target_id,
            "variant": variant,
            "windows": int(len(group)),
            "failed_windows": int(group["failed"].sum()),
            "truth_points": int(group["truth_points"].sum()),
            "missing_ratio": float(group["missing_ratio"].mean()),
        }
        for column in metric_columns:
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            row[column] = None if values.empty else float(values.mean())
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and backtest 19 target-specific Ridge-Delta benchmark models.")
    parser.add_argument("--db-host", default="10.30.220.12")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="bf_trend")
    parser.add_argument("--db-user", default="gl02_reader")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument("--training-days", type=float, default=14.0)
    parser.add_argument("--test-hours", type=float, default=48.0)
    parser.add_argument("--train-stride-minutes", type=int, default=5)
    parser.add_argument("--test-stride-minutes", type=int, default=120)
    parser.add_argument("--alpha", type=float, default=10.0)
    parser.add_argument("--model-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "models"))
    parser.add_argument("--output-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "results"))
    args = parser.parse_args()
    password = os.environ.get(args.db_password_env, "")
    if not password:
        raise SystemExit(f"missing database password environment variable: {args.db_password_env}")
    params = {
        "host": args.db_host,
        "port": args.db_port,
        "dbname": args.db_name,
        "user": args.db_user,
        "password": password,
        "connect_timeout": 12,
    }
    end = datetime.now()
    start = end - timedelta(days=args.training_days, minutes=CONTEXT_MINUTES + HORIZON_MINUTES)
    frame = load_core_frame(params, start, end)
    if frame.empty:
        raise SystemExit("no core variable history loaded")
    full_index = pd.date_range(frame.index.min().floor("min"), frame.index.max().floor("min"), freq="1min")
    frame = frame.reindex(full_index).interpolate(limit=5, limit_direction="forward").ffill(limit=15)
    split_time = frame.index.max() - pd.Timedelta(hours=args.test_hours)
    split_index = int(frame.index.searchsorted(split_time))
    max_index = len(frame) - HORIZON_MINUTES - 1
    train_indices = list(range(CONTEXT_MINUTES - 1, split_index - HORIZON_MINUTES, args.train_stride_minutes))
    test_indices = list(range(split_index, max_index + 1, args.test_stride_minutes))
    if len(train_indices) < 100 or not test_indices:
        raise SystemExit(f"insufficient windows train={len(train_indices)} test={len(test_indices)}")
    model_dir = Path(args.model_dir)
    output_dir = Path(args.output_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_rows: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    overall_start = time.perf_counter()
    for target_id in TARGET_IDS:
        for variant in ("target_only", "expert_sparse"):
            started = time.perf_counter()
            covariate_ids = [] if variant == "target_only" else [item for item in SPARSE_COVARIATES[target_id] if item in frame]
            x_rows: list[list[float]] = []
            y_rows: list[np.ndarray] = []
            feature_names: list[str] = []
            for index in train_indices:
                try:
                    names, features, truth, history = sample_at(frame, index, target_id, covariate_ids)
                except (KeyError, ValueError):
                    continue
                if not np.isfinite(truth).all() or not np.isfinite(history).all():
                    continue
                feature_names = names
                x_rows.append(features)
                y_rows.append(truth - history[-1])
            if len(x_rows) < 100:
                manifest.append({"target_id": target_id, "variant": variant, "status": "failed", "reason": f"only {len(x_rows)} training samples"})
                continue
            x = np.asarray(x_rows, dtype=float)
            y = np.asarray(y_rows, dtype=float)
            calibration_start = max(50, int(len(x) * 0.80))
            cal_fit = fit_ridge(x[:calibration_start], y[:calibration_start], args.alpha)
            cal_prediction = predict_matrix(x[calibration_start:], *cal_fit)
            residual = y[calibration_start:] - cal_prediction
            residual_q10 = np.quantile(residual, 0.10, axis=0)
            residual_q90 = np.quantile(residual, 0.90, axis=0)
            x_center, x_scale, y_center, coefficient = fit_ridge(x, y, args.alpha)
            trained_at = datetime.now().isoformat(sep=" ")
            model = {
                "schema": SCHEMA,
                "model": "ridge_delta",
                "target_id": target_id,
                "variant": variant,
                "covariate_ids": covariate_ids,
                "context_minutes": CONTEXT_MINUTES,
                "prediction_minutes": HORIZON_MINUTES,
                "feature_names": feature_names,
                "x_center": x_center.tolist(),
                "x_scale": x_scale.tolist(),
                "y_center": y_center.tolist(),
                "coefficient": coefficient.tolist(),
                "residual_q10": residual_q10.tolist(),
                "residual_q90": residual_q90.tolist(),
                "alpha": args.alpha,
                "training_samples": len(x_rows),
                "trained_at": trained_at,
                "training_time_start": frame.index[train_indices[0]].isoformat(sep=" "),
                "training_time_end": frame.index[train_indices[-1]].isoformat(sep=" "),
            }
            path = model_dir / f"ridge_delta__{target_id}__{variant}.json"
            path.write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            train_seconds = time.perf_counter() - started
            iqr = float(np.nanquantile(frame[target_id].iloc[:split_index], 0.75) - np.nanquantile(frame[target_id].iloc[:split_index], 0.25))
            for index in test_indices:
                predict_started = time.perf_counter()
                try:
                    _, features, truth, history = sample_at(frame, index, target_id, covariate_ids)
                    delta = predict_matrix(np.asarray([features]), x_center, x_scale, y_center, coefficient)[0]
                    p50 = history[-1] + delta
                    p10 = p50 + residual_q10
                    p90 = p50 + residual_q90
                    metrics = evaluate_window(history, truth, p10, p50, p90, iqr)
                except (KeyError, ValueError) as exc:
                    metrics = {"failed": True, "truth_points": 0, "missing_ratio": 1.0, "error": str(exc)}
                metrics.setdefault("missing_ratio", 0.0)
                for field in ("mae", "rmse", "iqr_nmae", "mase", "std_ratio", "diff_std_ratio", "direction_accuracy", "coverage_p10_p90", "pinball_p10", "pinball_p50", "pinball_p90", "wis_80", "mae_m00_30", "mae_m31_60", "mae_m61_120"):
                    metrics.setdefault(field, None)
                detail_rows.append({
                    "model": "ridge_delta",
                    "target_id": target_id,
                    "variant": variant,
                    "cutoff": frame.index[index].isoformat(sep=" "),
                    "covariate_count": len(covariate_ids),
                    "latency_ms": (time.perf_counter() - predict_started) * 1000.0,
                    **metrics,
                })
            manifest.append({
                "target_id": target_id,
                "variant": variant,
                "status": "ready",
                "covariate_ids": covariate_ids,
                "training_samples": len(x_rows),
                "train_seconds": train_seconds,
                "model_bytes": path.stat().st_size,
                "path": str(path),
            })
            print(f"TRAINED {target_id} {variant} samples={len(x_rows)} covariates={len(covariate_ids)} seconds={train_seconds:.2f}", flush=True)
    detail = pd.DataFrame(detail_rows)
    summary_rows = aggregate(detail) if not detail.empty else []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail_path = output_dir / f"ridge_delta_backtest_detail_{stamp}.csv"
    summary_path = output_dir / f"ridge_delta_backtest_summary_{stamp}.json"
    report_path = output_dir / f"ridge_delta_backtest_report_{stamp}.md"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary = {
        "requirement": "REQ-TS-FORECAST-MULTI-MODEL-BENCHMARK-20260808",
        "created_at": datetime.now().isoformat(sep=" "),
        "context_minutes": CONTEXT_MINUTES,
        "prediction_minutes": HORIZON_MINUTES,
        "training_days": args.training_days,
        "test_hours": args.test_hours,
        "train_windows": len(train_indices),
        "test_windows": len(test_indices),
        "elapsed_seconds": time.perf_counter() - overall_start,
        "manifest": manifest,
        "summary_by_target_variant": summary_rows,
        "detail_csv": str(detail_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_lines = [
        "# Ridge-Delta 19项时间序列回测报告",
        "",
        f"- 生成时间：{summary['created_at']}",
        f"- 上下文/预测：{CONTEXT_MINUTES}/{HORIZON_MINUTES}分钟",
        f"- 训练/测试窗口数：{len(train_indices)}/{len(test_indices)}",
        f"- 可用模型数：{sum(item.get('status') == 'ready' for item in manifest)}",
        "",
        "|变量|输入|IQR-NMAE|MASE|STD比|差分STD比|方向准确率|80%覆盖率|WIS|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary_rows:
        def show(name: str) -> str:
            value = item.get(name)
            return "-" if value is None else f"{value:.4f}"
        report_lines.append(f"|{item['target_id']}|{item['variant']}|{show('iqr_nmae')}|{show('mase')}|{show('std_ratio')}|{show('diff_std_ratio')}|{show('direction_accuracy')}|{show('coverage_p10_p90')}|{show('wis_80')}|")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("DETAIL", detail_path, flush=True)
    print("SUMMARY", summary_path, flush=True)
    print("REPORT", report_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

