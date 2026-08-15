from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from evaluate_ridge_fixed_cutoffs_19 import (  # noqa: E402
    CONTEXT_MINUTES,
    HORIZON_MINUTES,
    TARGET_IDS,
    clean_context,
    evaluate_window,
    load_model,
    predict_ridge,
    read_cutoffs,
)
from run_chronos_sparse_prepredict import SPARSE_COVARIATES  # noqa: E402


MODEL_NAMES = ("chronos2", "ridge_expert_sparse", "ridge_target_only")
QUANTILES = ("p10", "p50", "p90")


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        url.rstrip("/") + "/api/chronos/predict",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def cached_chronos_prediction(cache_dir: Path, url: str, contexts: dict[str, np.ndarray], cutoff: pd.Timestamp, timeout: float) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"chronos2_{cutoff.strftime('%Y%m%d_%H%M')}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            result = post_json(url, chronos_payload(contexts, cutoff), timeout)
            temporary = cache_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            temporary.replace(cache_path)
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"CHRONOS_RETRY cutoff={cutoff} attempt={attempt} error={type(exc).__name__}: {exc}", flush=True)
            if attempt < 3:
                time.sleep(5 * attempt)
    raise RuntimeError(f"Chronos failed after 3 attempts for {cutoff}") from last_error


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
            "feature_engine": "REQ-TS-FORECAST-SEGMENTED-ENSEMBLE-20260811",
            "cutoff_time": cutoff.isoformat(sep=" "),
            "future_timestamps": [(cutoff + pd.Timedelta(minutes=index)).isoformat(sep=" ") for index in range(1, HORIZON_MINUTES + 1)],
        })
    return {"jobs": jobs, "request": {"target_ids": list(contexts), "context_minutes": CONTEXT_MINUTES, "prediction_minutes": HORIZON_MINUTES, "variant": "target_only"}}


def segmented_weights(horizon: int = HORIZON_MINUTES, smooth: bool = True) -> np.ndarray:
    weights = np.zeros((horizon, len(MODEL_NAMES)), dtype=float)
    if not smooth:
        weights[:30, 0] = 1.0
        weights[30:60, 1] = 1.0
        weights[60:, 2] = 1.0
        return weights

    weights[:25, 0] = 1.0
    transition_1 = np.linspace(1.0, 0.0, 11)
    weights[25:36, 0] = transition_1
    weights[25:36, 1] = 1.0 - transition_1
    weights[36:55, 1] = 1.0
    transition_2 = np.linspace(1.0, 0.0, 11)
    weights[55:66, 1] = transition_2
    weights[55:66, 2] = 1.0 - transition_2
    weights[66:, 2] = 1.0
    return weights


def blend_forecasts(forecasts: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]], smooth: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    weights = segmented_weights(smooth=smooth)
    output = []
    for quantile_index in range(3):
        values = np.stack([forecasts[name][quantile_index] for name in MODEL_NAMES], axis=1)
        output.append(np.sum(values * weights, axis=1))
    return tuple(output)  # type: ignore[return-value]


def metric_record(model: str, target_id: str, cutoff: pd.Timestamp, history: np.ndarray, truth: np.ndarray, forecast: tuple[np.ndarray, np.ndarray, np.ndarray], iqr: float) -> dict[str, Any]:
    metrics = evaluate_window(history, truth, *forecast, iqr)
    return {"model": model, "target_id": target_id, "cutoff": cutoff.isoformat(sep=" "), **metrics}


def macro_summary(detail: pd.DataFrame) -> list[dict[str, Any]]:
    fields = ("mae", "rmse", "iqr_nmae", "std_ratio", "diff_std_ratio", "direction_accuracy", "coverage_p10_p90", "wis_80", "mae_m00_30", "mae_m31_60", "mae_m61_120")
    rows = []
    for model, group in detail.groupby("model", sort=False):
        row: dict[str, Any] = {"model": model, "windows": int(len(group)), "targets": int(group["target_id"].nunique())}
        for field in fields:
            values = pd.to_numeric(group[field], errors="coerce").dropna()
            row[field] = None if values.empty else float(values.mean())
        rows.append(row)
    return rows


def plot_latest(raw: pd.DataFrame, output_path: Path) -> None:
    cutoff = pd.Timestamp(raw["cutoff"].max())
    subset = raw[raw["cutoff"] == cutoff.isoformat(sep=" ")]
    figure, axes = plt.subplots(len(TARGET_IDS), 1, figsize=(18, 26), sharex=True)
    colors = {"chronos2": "#2f8cff", "ridge_expert_sparse": "#ffad32", "ridge_target_only": "#39d3ae", "segmented_smooth": "#ff5e6c"}
    for axis, target_id in zip(axes, TARGET_IDS):
        target = subset[subset["target_id"] == target_id]
        truth = target[target["model"] == "truth"].sort_values("minute")
        axis.plot(truth["minute"], truth["value"], color="#e7edf6", linewidth=1.4, label="Actual")
        for model, color in colors.items():
            series = target[(target["model"] == model) & (target["quantile"] == "p50")].sort_values("minute")
            axis.plot(series["minute"], series["value"], color=color, linewidth=1.0 if model != "segmented_smooth" else 1.8, alpha=0.8 if model != "segmented_smooth" else 1.0, label=model)
        axis.axvline(30, color="#718096", linewidth=0.7, linestyle=":")
        axis.axvline(60, color="#718096", linewidth=0.7, linestyle=":")
        axis.set_ylabel(target_id, rotation=0, ha="right", va="center")
        axis.grid(alpha=0.15)
    axes[0].legend(loc="upper right", ncol=5, fontsize=8)
    axes[-1].set_xlabel("Forecast minute")
    figure.suptitle(f"19-target segmented ensemble vs actual | cutoff {cutoff}", fontsize=16)
    figure.tight_layout(rect=(0, 0, 1, 0.985))
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare segmented Chronos/Ridge ensemble on the fixed 19-target cutoffs.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--cutoff-summary", required=True)
    parser.add_argument("--chronos-url", default="http://10.30.220.12:8777")
    parser.add_argument("--model-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "models"))
    parser.add_argument("--output-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "results"))
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--chronos-cache-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "results" / "chronos_segmented_cache"))
    args = parser.parse_args()

    frame = pd.read_csv(args.input_csv, index_col="ts", parse_dates=["ts"])
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame = frame.reindex(pd.date_range(frame.index.min().floor("min"), frame.index.max().floor("min"), freq="1min"))
    cutoffs = read_cutoffs(Path(args.cutoff_summary))
    models = {
        variant: {target: load_model(Path(args.model_dir), target, variant) for target in TARGET_IDS}
        for variant in ("target_only", "expert_sparse")
    }
    detail_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []

    for cutoff in cutoffs:
        contexts: dict[str, np.ndarray] = {}
        truths: dict[str, np.ndarray] = {}
        iqrs: dict[str, float] = {}
        for target_id in TARGET_IDS:
            context = frame[target_id].loc[(frame.index > cutoff - pd.Timedelta(minutes=CONTEXT_MINUTES)) & (frame.index <= cutoff)]
            contexts[target_id] = clean_context(context)
            truths[target_id] = pd.to_numeric(frame[target_id].loc[(frame.index > cutoff) & (frame.index <= cutoff + pd.Timedelta(minutes=HORIZON_MINUTES))], errors="coerce").to_numpy(dtype=float)
            history_values = frame[target_id].loc[frame.index <= cutoff].tail(30 * 24 * 60).to_numpy(dtype=float)
            q1, q3 = np.nanquantile(history_values, [0.25, 0.75])
            iqrs[target_id] = float(q3 - q1)

        started = time.perf_counter()
        chronos_result = cached_chronos_prediction(Path(args.chronos_cache_dir), args.chronos_url, contexts, cutoff, args.timeout_seconds)
        chronos_predictions = {str(item.get("target_id")): item for item in chronos_result.get("predictions") or []}
        if set(chronos_predictions) != set(TARGET_IDS):
            missing = sorted(set(TARGET_IDS) - set(chronos_predictions))
            raise RuntimeError(f"Chronos response missing targets: {missing}")

        for target_id in TARGET_IDS:
            covariates = {covariate: clean_context(frame[covariate].loc[(frame.index > cutoff - pd.Timedelta(minutes=CONTEXT_MINUTES)) & (frame.index <= cutoff)]) for covariate in SPARSE_COVARIATES.get(target_id, [])}
            prediction = chronos_predictions[target_id]
            forecasts = {
                "chronos2": tuple(np.asarray(prediction[name], dtype=float)[:HORIZON_MINUTES] for name in QUANTILES),
                "ridge_expert_sparse": predict_ridge(models["expert_sparse"][target_id], contexts[target_id], covariates),
                "ridge_target_only": predict_ridge(models["target_only"][target_id], contexts[target_id], {}),
            }
            forecasts["segmented_hard"] = blend_forecasts(forecasts, smooth=False)
            forecasts["segmented_smooth"] = blend_forecasts(forecasts, smooth=True)
            for model_name, forecast in forecasts.items():
                detail_rows.append(metric_record(model_name, target_id, cutoff, contexts[target_id], truths[target_id], forecast, iqrs[target_id]))
                for quantile, values in zip(QUANTILES, forecast):
                    raw_rows.extend({"cutoff": cutoff.isoformat(sep=" "), "target_id": target_id, "minute": minute, "model": model_name, "quantile": quantile, "value": float(value)} for minute, value in enumerate(values, 1))
            raw_rows.extend({"cutoff": cutoff.isoformat(sep=" "), "target_id": target_id, "minute": minute, "model": "truth", "quantile": "actual", "value": float(value)} for minute, value in enumerate(truths[target_id], 1))
        print(f"CUTOFF {cutoff} complete seconds={time.perf_counter() - started:.1f}", flush=True)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail = pd.DataFrame(detail_rows)
    raw = pd.DataFrame(raw_rows)
    summary = macro_summary(detail)
    detail_path = output_dir / f"segmented_ensemble_detail_{stamp}.csv"
    raw_path = output_dir / f"segmented_ensemble_raw_{stamp}.csv.gz"
    summary_path = output_dir / f"segmented_ensemble_summary_{stamp}.json"
    plot_path = output_dir / f"segmented_ensemble_latest_curves_{stamp}.png"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    raw.to_csv(raw_path, index=False, compression="gzip", encoding="utf-8")
    summary_path.write_text(json.dumps({"created_at": datetime.now().isoformat(sep=" "), "cutoffs": [item.isoformat(sep=" ") for item in cutoffs], "smooth_transition_minutes": [26, 35, 56, 65], "summary": summary, "detail_csv": str(detail_path), "raw_csv_gz": str(raw_path)}, ensure_ascii=False, indent=2), encoding="utf-8")
    plot_latest(raw, plot_path)
    print("SUMMARY", summary_path, flush=True)
    print("DETAIL", detail_path, flush=True)
    print("RAW", raw_path, flush=True)
    print("PLOT", plot_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
