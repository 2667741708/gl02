from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
import psutil
import torch
from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from benchmark_timesfm25_zero_shot_19 import (  # noqa: E402
    HORIZON_MINUTES,
    TARGET_IDS,
    baseline_interval,
    chronos_payload,
    clean_context,
    metric_row,
    post_json,
    summarize,
)


def ttm_input(context: np.ndarray) -> np.ndarray:
    if len(context) != 480:
        raise ValueError(f"TTM adapter requires 480 real points, received {len(context)}")
    return np.pad(context, (32, 0), mode="edge")


def ttm_interval(history: np.ndarray, point: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    baseline_low, baseline_mid, baseline_high = baseline_interval(history, HORIZON_MINUTES)
    return point + (baseline_low - baseline_mid), point, point + (baseline_high - baseline_mid)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark IBM TTM R2 zero-shot, Chronos-2 and LastValue on identical 19-target windows.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--chronos-url", default="http://127.0.0.1:8777")
    parser.add_argument("--test-windows", type=int, default=24)
    parser.add_argument("--stride-minutes", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--output-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "results"))
    args = parser.parse_args()

    frame = pd.read_csv(args.input_csv, index_col="ts", parse_dates=["ts"])
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame = frame.reindex(pd.date_range(frame.index.min().floor("min"), frame.index.max().floor("min"), freq="1min"))
    latest_cutoff = frame.index.max().floor("min") - pd.Timedelta(minutes=HORIZON_MINUTES)
    cutoffs = []
    candidate = latest_cutoff
    earliest = frame.index.min() + pd.Timedelta(minutes=480)
    while candidate >= earliest and len(cutoffs) < args.test_windows:
        valid = True
        for target_id in TARGET_IDS:
            context = frame[target_id].loc[(frame.index > candidate - pd.Timedelta(minutes=480)) & (frame.index <= candidate)]
            truth = pd.to_numeric(frame[target_id].loc[(frame.index > candidate) & (frame.index <= candidate + pd.Timedelta(minutes=HORIZON_MINUTES))], errors="coerce")
            try:
                clean_context(context)
            except ValueError:
                valid = False
                break
            if len(truth) != HORIZON_MINUTES or truth.notna().sum() < HORIZON_MINUTES // 2:
                valid = False
                break
        if valid:
            cutoffs.append(candidate)
        else:
            print(f"SKIP_CUTOFF {candidate} incomplete_context_or_truth", flush=True)
        candidate -= pd.Timedelta(minutes=args.stride_minutes)
    cutoffs = sorted(cutoffs)
    if len(cutoffs) < args.test_windows:
        raise RuntimeError(f"only {len(cutoffs)} valid cutoffs found; requested {args.test_windows}")

    process = psutil.Process()
    load_started = time.perf_counter()
    model = TinyTimeMixerForPrediction.from_pretrained(args.model_path, local_files_only=True)
    model.eval()
    model_load_seconds = time.perf_counter() - load_started
    model_bytes = int(sum(parameter.numel() * parameter.element_size() for parameter in model.parameters()))
    detail_rows = []

    for cutoff in cutoffs:
        contexts = {}
        truths = {}
        iqrs = {}
        for target_id in TARGET_IDS:
            context = frame[target_id].loc[(frame.index > cutoff - pd.Timedelta(minutes=480)) & (frame.index <= cutoff)]
            truth = pd.to_numeric(frame[target_id].loc[(frame.index > cutoff) & (frame.index <= cutoff + pd.Timedelta(minutes=HORIZON_MINUTES))], errors="coerce").to_numpy(dtype=float)
            if len(truth) != HORIZON_MINUTES:
                raise RuntimeError(f"truth length mismatch {target_id} {cutoff}: {len(truth)}")
            contexts[target_id] = clean_context(context)
            truths[target_id] = truth
            history_values = frame[target_id].loc[frame.index <= cutoff].tail(30 * 24 * 60).to_numpy(dtype=float)
            q1, q3 = np.nanquantile(history_values, [0.25, 0.75])
            iqrs[target_id] = float(q3 - q1)

        batch = np.stack([ttm_input(contexts[target]) for target in TARGET_IDS], axis=0)
        tensor = torch.tensor(batch, dtype=torch.float32).unsqueeze(-1)
        ttm_started = time.perf_counter()
        with torch.no_grad():
            output = model(past_values=tensor, return_dict=True)
        points = output.prediction_outputs.detach().cpu().numpy()[:, :HORIZON_MINUTES, 0]
        ttm_latency = (time.perf_counter() - ttm_started) * 1000.0 / len(TARGET_IDS)
        resource = {
            "model_bytes": model_bytes,
            "peak_ram_mb": process.memory_info().rss / 1024.0 / 1024.0,
            "peak_gpu_mb": 0.0,
        }
        for target_index, target_id in enumerate(TARGET_IDS):
            forecasts = ttm_interval(contexts[target_id], points[target_index])
            detail_rows.append(metric_row("ibm_ttm_r2_zero_shot", target_id, cutoff, contexts[target_id], truths[target_id], forecasts, iqrs[target_id], ttm_latency, resource))
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
        print(f"CUTOFF {cutoff} ttm_ms_per_series={ttm_latency:.3f} chronos_predictions={len(predictions)}", flush=True)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail = pd.DataFrame(detail_rows)
    summary_rows = summarize(detail)
    detail_path = output_dir / f"ttm_chronos2_zero_shot_detail_{stamp}.csv"
    summary_path = output_dir / f"ttm_chronos2_zero_shot_summary_{stamp}.json"
    report_path = output_dir / f"ttm_chronos2_zero_shot_report_{stamp}.md"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary = {
        "requirement": "REQ-TS-FORECAST-MULTI-MODEL-BENCHMARK-20260808",
        "created_at": datetime.now().isoformat(sep=" "),
        "model_path": args.model_path,
        "model_load_seconds": model_load_seconds,
        "context_real_points": 480,
        "context_adapter": "left_pad_first_value_32_to_ttm512",
        "prediction_minutes": HORIZON_MINUTES,
        "interval_source": "historical_first_difference_calibration_not_native_ttm",
        "cutoffs": [item.isoformat(sep=" ") for item in cutoffs],
        "summary_by_model_target": summary_rows,
        "detail_csv": str(detail_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        "# IBM TTM R2、Chronos-2与LastValue同切点零样本回测",
        "",
        f"- 模型加载耗时：{model_load_seconds:.2f}秒",
        "- 真实上下文：480分钟；TTM适配：左侧首值填充32点到512",
        "- 预测：模型192点中截取前120点",
        "- TTM区间：历史一阶差分校准，不是TTM原生概率输出",
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
