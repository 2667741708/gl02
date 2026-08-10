from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys
import time
from typing import Any
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import psutil
import psycopg
import torch


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from timeseries_model_contract import CONTEXT_MINUTES, HORIZON_MINUTES, quantile  # noqa: E402


MODEL_ID = "google/timesfm-2.5-200m-transformers"
TARGET_IDS = [
    "P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "Q_blast", "P_blast_cold", "P_blast", "T_blast", "T_top",
    "T_top_A", "T_top_B", "T_top_C", "T_top_D", "PI", "DP_total",
    "DP_upper", "DP_lower", "GasUtil",
]
RAW_TARGET_IDS = [item for item in TARGET_IDS if item != "T_top"]


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        url.rstrip("/") + "/api/chronos/predict",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def load_core_frame(conn_params: dict[str, Any], start: datetime, end: datetime) -> pd.DataFrame:
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
    values = pd.DataFrame(rows, columns=["variable_name", "ts", "value"])
    if values.empty:
        return pd.DataFrame()
    frame = values.pivot_table(index="ts", columns="variable_name", values="value", aggfunc="last").sort_index()
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame["T_top"] = frame[["T_top_A", "T_top_B", "T_top_C", "T_top_D"]].mean(axis=1)
    return frame


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return None if not math.isfinite(denominator) or abs(denominator) <= 1e-12 else float(numerator / denominator)


def pinball(truth: np.ndarray, prediction: np.ndarray, probability: float) -> float:
    error = truth - prediction
    return float(np.mean(np.maximum(probability * error, (probability - 1.0) * error)))


def evaluate_window(history: np.ndarray, truth: np.ndarray, p10: np.ndarray, p50: np.ndarray, p90: np.ndarray, iqr: float) -> dict[str, Any]:
    valid = np.isfinite(truth) & np.isfinite(p10) & np.isfinite(p50) & np.isfinite(p90)
    if valid.sum() < HORIZON_MINUTES // 2:
        return {"failed": True, "truth_points": int(valid.sum())}
    t, lo, mid, hi = truth[valid], p10[valid], p50[valid], p90[valid]
    error = mid - t
    absolute_error = np.abs(error)
    scale = max(float(iqr), abs(float(np.median(history))) * 0.01, 1e-6)
    naive_scale = float(np.mean(np.abs(np.diff(history[np.isfinite(history)]))))
    truth_diff = np.diff(np.r_[history[-1], t])
    prediction_diff = np.diff(np.r_[history[-1], mid])
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


def clean_context(values: pd.Series) -> np.ndarray:
    series = pd.to_numeric(values, errors="coerce").interpolate(limit=5, limit_direction="forward").ffill(limit=15)
    if len(series) < CONTEXT_MINUTES or series.isna().any():
        raise ValueError("incomplete 480-minute context")
    return series.to_numpy(dtype=np.float32)


def output_quantiles(model: Any, outputs: Any, horizon: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = outputs.mean_predictions.detach().cpu().numpy()[:, :horizon]
    full = outputs.full_predictions.detach().cpu().numpy()[:, :horizon, :]
    probabilities = [float(item) for item in model.config.quantiles]
    offset = 1 if full.shape[-1] == len(probabilities) + 1 else 0

    def select(probability: float, fallback: np.ndarray) -> np.ndarray:
        if probability not in probabilities:
            return fallback
        return full[:, :, probabilities.index(probability) + offset]

    p10 = select(0.1, mean)
    p50 = select(0.5, mean)
    p90 = select(0.9, mean)
    return p10, p50, p90


def baseline_interval(history: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    differences = np.diff(history)
    low = quantile(differences, 0.10)
    center = quantile(differences, 0.50)
    high = quantile(differences, 0.90)
    scale = np.sqrt(np.arange(1, horizon + 1, dtype=float))
    p50 = np.full(horizon, history[-1], dtype=float)
    return p50 + (low - center) * scale, p50, p50 + (high - center) * scale


def chronos_payload(contexts: dict[str, np.ndarray], cutoff: pd.Timestamp) -> dict[str, Any]:
    jobs = []
    for target_id, values in contexts.items():
        jobs.append({
            "target_id": target_id,
            "target_name": target_id,
            "target": {"id": target_id, "name": target_id, "values": values.astype(float).tolist(), "nonnull_count": len(values)},
            "covariates": [],
            "context_minutes": len(values),
            "prediction_minutes": HORIZON_MINUTES,
            "feature_type": "benchmark_target_only",
            "feature_engine": "REQ-TS-FORECAST-MULTI-MODEL-BENCHMARK-20260808",
            "cutoff_time": cutoff.isoformat(sep=" "),
            "future_timestamps": [
                (cutoff + pd.Timedelta(minutes=index)).isoformat(sep=" ")
                for index in range(1, HORIZON_MINUTES + 1)
            ],
        })
    return {
        "jobs": jobs,
        "request": {
            "target_ids": list(contexts),
            "context_minutes": CONTEXT_MINUTES,
            "prediction_minutes": HORIZON_MINUTES,
            "variant": "target_only",
        },
    }


def metric_row(model_name: str, target_id: str, cutoff: pd.Timestamp, history: np.ndarray, truth: np.ndarray, forecasts: tuple[np.ndarray, np.ndarray, np.ndarray], iqr: float, latency_ms: float, resource: dict[str, Any]) -> dict[str, Any]:
    p10, p50, p90 = forecasts
    metrics = evaluate_window(history, truth, p10, p50, p90, iqr)
    metrics.setdefault("missing_ratio", 0.0)
    for field in ("mae", "rmse", "iqr_nmae", "mase", "std_ratio", "diff_std_ratio", "direction_accuracy", "coverage_p10_p90", "pinball_p10", "pinball_p50", "pinball_p90", "wis_80", "mae_m00_30", "mae_m31_60", "mae_m61_120"):
        metrics.setdefault(field, None)
    return {
        "model": model_name,
        "target_id": target_id,
        "variant": "target_only",
        "cutoff": cutoff.isoformat(sep=" "),
        "latency_ms": latency_ms,
        "train_seconds": 0.0,
        **resource,
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
    for (model_name, target_id), group in detail.groupby(["model", "target_id"], sort=False):
        row: dict[str, Any] = {
            "model": model_name,
            "target_id": target_id,
            "variant": "target_only",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark TimesFM 2.5 zero-shot, Chronos-2 and LastValue on the same 19-target windows.")
    parser.add_argument("--db-host", default="127.0.0.1")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="bf_trend")
    parser.add_argument("--db-user", default="gl02_reader")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument("--input-csv", default="", help="Optional prepared 19-target frame; bypasses database access.")
    parser.add_argument("--chronos-url", default="http://127.0.0.1:8777")
    parser.add_argument("--test-windows", type=int, default=24)
    parser.add_argument("--stride-minutes", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--output-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "results"))
    args = parser.parse_args()
    if args.input_csv:
        frame = pd.read_csv(args.input_csv, index_col="ts", parse_dates=["ts"])
        frame.index = pd.to_datetime(frame.index).tz_localize(None)
    else:
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
        lookback = timedelta(minutes=CONTEXT_MINUTES + HORIZON_MINUTES + args.test_windows * args.stride_minutes + 60)
        frame = load_core_frame(params, datetime.now() - lookback, datetime.now())
    if frame.empty:
        raise SystemExit("no historical frame was loaded")
    frame = frame.reindex(pd.date_range(frame.index.min().floor("min"), frame.index.max().floor("min"), freq="1min"))
    latest_cutoff = frame.index.max().floor("min") - pd.Timedelta(minutes=HORIZON_MINUTES)
    cutoffs = [latest_cutoff - pd.Timedelta(minutes=args.stride_minutes * index) for index in reversed(range(args.test_windows))]
    process = psutil.Process()
    load_started = time.perf_counter()
    from transformers import TimesFm2_5ModelForPrediction

    model = TimesFm2_5ModelForPrediction.from_pretrained(args.model_id, device_map="cpu")
    model.eval()
    model_load_seconds = time.perf_counter() - load_started
    model_bytes = int(sum(parameter.numel() * parameter.element_size() for parameter in model.parameters()))
    detail_rows: list[dict[str, Any]] = []
    for cutoff in cutoffs:
        contexts: dict[str, np.ndarray] = {}
        truths: dict[str, np.ndarray] = {}
        iqrs: dict[str, float] = {}
        for target_id in TARGET_IDS:
            context = frame[target_id].loc[(frame.index > cutoff - pd.Timedelta(minutes=CONTEXT_MINUTES)) & (frame.index <= cutoff)]
            truth = pd.to_numeric(frame[target_id].loc[(frame.index > cutoff) & (frame.index <= cutoff + pd.Timedelta(minutes=HORIZON_MINUTES))], errors="coerce").to_numpy(dtype=float)
            if len(truth) != HORIZON_MINUTES:
                raise RuntimeError(f"truth length mismatch {target_id} {cutoff}: {len(truth)}")
            contexts[target_id] = clean_context(context)
            truths[target_id] = truth
            history_values = frame[target_id].loc[frame.index <= cutoff].tail(30 * 24 * 60)
            q1, q3 = np.nanquantile(history_values.to_numpy(dtype=float), [0.25, 0.75])
            iqrs[target_id] = float(q3 - q1)
        timesfm_started = time.perf_counter()
        inputs = [torch.tensor(contexts[target], dtype=torch.float32) for target in TARGET_IDS]
        with torch.no_grad():
            outputs = model(past_values=inputs, forecast_context_len=CONTEXT_MINUTES, return_dict=True)
        timesfm_forecasts = output_quantiles(model, outputs, HORIZON_MINUTES)
        timesfm_latency = (time.perf_counter() - timesfm_started) * 1000.0 / len(TARGET_IDS)
        resource = {
            "model_bytes": model_bytes,
            "peak_ram_mb": process.memory_info().rss / 1024.0 / 1024.0,
            "peak_gpu_mb": 0.0,
        }
        for target_index, target_id in enumerate(TARGET_IDS):
            forecasts = tuple(values[target_index] for values in timesfm_forecasts)
            detail_rows.append(metric_row("timesfm_2_5_zero_shot", target_id, cutoff, contexts[target_id], truths[target_id], forecasts, iqrs[target_id], timesfm_latency, resource))
            baseline = baseline_interval(contexts[target_id], HORIZON_MINUTES)
            detail_rows.append(metric_row("last_value", target_id, cutoff, contexts[target_id], truths[target_id], baseline, iqrs[target_id], 0.02, {"model_bytes": 0, "peak_ram_mb": 0.0, "peak_gpu_mb": 0.0}))
        chronos_started = time.perf_counter()
        chronos_result = post_json(args.chronos_url, chronos_payload(contexts, cutoff), args.timeout_seconds)
        chronos_latency = (time.perf_counter() - chronos_started) * 1000.0 / len(TARGET_IDS)
        predictions = {str(item.get("target_id")): item for item in chronos_result.get("predictions") or []}
        for target_id in TARGET_IDS:
            prediction = predictions.get(target_id)
            if not prediction:
                continue
            forecasts = tuple(np.asarray(prediction.get(name) or [], dtype=float)[:HORIZON_MINUTES] for name in ("p10", "p50", "p90"))
            if any(len(values) != HORIZON_MINUTES for values in forecasts):
                continue
            detail_rows.append(metric_row("chronos2_zero_shot", target_id, cutoff, contexts[target_id], truths[target_id], forecasts, iqrs[target_id], chronos_latency, {"model_bytes": 0, "peak_ram_mb": 0.0, "peak_gpu_mb": 0.0}))
        print(f"CUTOFF {cutoff} timesfm_ms_per_series={timesfm_latency:.2f} chronos_predictions={len(predictions)}", flush=True)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail = pd.DataFrame(detail_rows)
    summary_rows = summarize(detail)
    detail_path = output_dir / f"timesfm25_chronos2_zero_shot_detail_{stamp}.csv"
    summary_path = output_dir / f"timesfm25_chronos2_zero_shot_summary_{stamp}.json"
    report_path = output_dir / f"timesfm25_chronos2_zero_shot_report_{stamp}.md"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary = {
        "requirement": "REQ-TS-FORECAST-MULTI-MODEL-BENCHMARK-20260808",
        "created_at": datetime.now().isoformat(sep=" "),
        "model_id": args.model_id,
        "model_load_seconds": model_load_seconds,
        "context_minutes": CONTEXT_MINUTES,
        "prediction_minutes": HORIZON_MINUTES,
        "cutoffs": [item.isoformat(sep=" ") for item in cutoffs],
        "summary_by_model_target": summary_rows,
        "detail_csv": str(detail_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        "# TimesFM 2.5、Chronos-2与LastValue同切点零样本回测",
        "",
        f"- 模型加载耗时：{model_load_seconds:.2f}秒",
        f"- 上下文/预测：{CONTEXT_MINUTES}/{HORIZON_MINUTES}分钟",
        f"- 切点数：{len(cutoffs)}",
        "",
        "|模型|变量|IQR-NMAE|MASE|STD比|差分STD比|方向准确率|80%覆盖率|WIS|延迟ms/序列|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary_rows:
        def show(field: str) -> str:
            value = item.get(field)
            return "-" if value is None else f"{value:.4f}"
        report.append(f"|{item['model']}|{item['target_id']}|{show('iqr_nmae')}|{show('mase')}|{show('std_ratio')}|{show('diff_std_ratio')}|{show('direction_accuracy')}|{show('coverage_p10_p90')}|{show('wis_80')}|{show('latency_ms')}|")
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("DETAIL", detail_path, flush=True)
    print("SUMMARY", summary_path, flush=True)
    print("REPORT", report_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
