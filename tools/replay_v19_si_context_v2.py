"""Corrected V19 recent replay with normalized timestamp keys."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from si_semantic_engine.prospective import build_inference_feature_frame
from si_semantic_engine.train_v6 import _history_baseline
from si_semantic_engine.v19_context_features import build_mean_si_history_context, merge_v19_context_features


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    return {
        "rows": int(len(actual)),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "hit_rate_abs_le_002": float(np.mean(np.abs(error) <= 0.02)),
        "hit_rate_abs_le_005": float(np.mean(np.abs(error) <= 0.05)),
        "pearson": float(np.corrcoef(actual, predicted)[0, 1]) if len(actual) > 1 else np.nan,
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="回放V19平均Si上下文预测曲线。")
    for name in ("prediction_rows", "heat_targets", "samples", "sensor_catalog", "temporal_dir", "context", "model", "output_dir"):
        cli.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    prediction_rows = pd.read_csv(args.prediction_rows.resolve(), low_memory=False, encoding="utf-8-sig")
    all_targets = pd.read_csv(args.heat_targets.resolve(), low_memory=False, encoding="utf-8-sig")
    samples = pd.read_csv(args.samples.resolve(), low_memory=False, encoding="utf-8-sig")
    for frame in (prediction_rows, all_targets):
        frame["official_meltno"] = frame["official_meltno"].astype(str)
        frame["prediction_cutoff_ts"] = pd.to_datetime(frame["prediction_cutoff_ts"], errors="raise")
    context = pd.read_csv(args.context.resolve(), low_memory=False, encoding="utf-8-sig")
    context["official_meltno"] = context["official_meltno"].astype(str)
    history = build_mean_si_history_context(all_targets)
    history_cols = [column for column in history if column.startswith("history_mean__")]
    context = context.drop(columns=[column for column in history_cols if column in context], errors="ignore")
    context = merge_v19_context_features(context, history)
    features, feature_audit = build_inference_feature_frame(
        prediction_rows, all_targets, samples, args.sensor_catalog.resolve(), args.temporal_dir.resolve()
    )
    features = merge_v19_context_features(features, context)
    bundle = joblib.load(args.model.resolve())
    baseline = _history_baseline(features, fallback=float(bundle["fallback"])).to_numpy(float)
    required = set(bundle["direct_features"]) | set(bundle["thermal_features"]) | set(bundle["lgbm_features"])
    missing = sorted(required - set(features.columns))
    if missing:
        raise RuntimeError(f"V19回放缺少特征：{missing[:20]}")
    components = {
        "direct": bundle["direct_model"].predict(features[bundle["direct_features"]]),
        "thermal_xgb": bundle["thermal_model"].predict(features[bundle["thermal_features"]]) + baseline,
        "lgbm_huber7": bundle["lgbm_models"]["lgbm_huber7"].predict(features[bundle["lgbm_features"]]) + baseline,
        "lgbm_huber15_decay90": bundle["lgbm_models"]["lgbm_huber15_decay90"].predict(features[bundle["lgbm_features"]]) + baseline,
        "history": baseline,
    }
    prediction = sum(float(bundle["weights"][name]) * np.asarray(values, dtype=float) for name, values in components.items())
    actual = all_targets[["official_meltno", "prediction_cutoff_ts", "target__Si_mean"]].copy()
    curve = prediction_rows[["official_meltno", "prediction_cutoff_ts"]].merge(actual, on=["official_meltno", "prediction_cutoff_ts"], how="inner", validate="one_to_one")
    curve["prediction__Si_mean"] = prediction
    curve = curve.sort_values(["prediction_cutoff_ts", "official_meltno"], kind="stable").rename(columns={"target__Si_mean": "actual__Si_mean"})
    curve["absolute_error"] = (curve["prediction__Si_mean"] - curve["actual__Si_mean"]).abs()
    curve.to_csv(output / "si_mean_actual_vs_prediction_v19.csv", index=False, encoding="utf-8-sig")
    plt.figure(figsize=(14, 6), dpi=160)
    timestamps = pd.to_datetime(curve["prediction_cutoff_ts"])
    plt.plot(timestamps, curve["actual__Si_mean"], label="实际平均Si", linewidth=1.7)
    plt.plot(timestamps, curve["prediction__Si_mean"], label="V19预测平均Si", linewidth=1.5)
    plt.grid(alpha=0.25)
    plt.ylabel("Si（%）")
    plt.xlabel("炉次开口时间")
    plt.legend()
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    plt.tight_layout()
    plt.savefig(output / "si_mean_actual_vs_prediction_v19.png")
    plt.close()
    actual_values = curve["actual__Si_mean"].to_numpy(float)
    predicted_values = curve["prediction__Si_mean"].to_numpy(float)
    prospective = curve.loc[curve["prediction_cutoff_ts"] >= pd.Timestamp("2026-07-27")]
    result = {
        "requirement_id": "REQ-SI-V19-CONTEXT-ABLATION-20260806",
        "status": "experimental_offline_readonly",
        "window": {"start": curve["prediction_cutoff_ts"].min(), "end": curve["prediction_cutoff_ts"].max()},
        "all_latest_15_days": metrics(actual_values, predicted_values),
        "strictly_after_2026_07_27": metrics(prospective["actual__Si_mean"].to_numpy(float), prospective["prediction__Si_mean"].to_numpy(float)) if len(prospective) > 1 else None,
        "weights": bundle["weights"],
        "context_groups": bundle["context_groups"],
        "feature_audit": feature_audit,
        "chemistry_lineage_status": "batch_to_heat_unverified_time_background_only",
    }
    (output / "metrics_v19_recent.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"ok": True, "rows": len(curve), "metrics": result["all_latest_15_days"]}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
