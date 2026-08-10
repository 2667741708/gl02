"""Rebuild the average-Si prediction curve from cached read-only inputs.

Requirement: REQ-SI-HEAT-AVERAGE-CURVE-20260806
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from run_22012_si_average_curve import (
    DEFAULT_CATALOG,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT,
    PROSPECTIVE_BOUNDARY,
    _json_default,
    build_inference_feature_frame,
    predict_mean_v9,
    regression_metrics,
    render_curve,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="复用已提取特征重新生成逐炉平均Si真实/预测曲线。"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--sensor-catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    input_dir = output_dir / "inputs"
    targets = pd.read_csv(
        input_dir / "heat_targets_mean.csv", low_memory=False, encoding="utf-8-sig"
    )
    samples = pd.read_csv(
        input_dir / "formal_samples.csv", low_memory=False, encoding="utf-8-sig"
    )
    prediction_rows = pd.read_csv(
        input_dir / "prediction_rows.csv", low_memory=False, encoding="utf-8-sig"
    )
    for frame, columns in (
        (targets, ("prediction_cutoff_ts", "label_available_ts")),
        (samples, ("open_ts", "result_ts")),
        (prediction_rows, ("prediction_cutoff_ts", "feature_cutoff_ts")),
    ):
        for column in columns:
            if column in frame:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
    inference, feature_audit = build_inference_feature_frame(
        prediction_rows,
        targets,
        samples,
        args.sensor_catalog.resolve(),
        output_dir / "temporal_stats",
    )
    predictions = predict_mean_v9(inference, args.model.resolve())
    recent = prediction_rows[
        [
            "official_meltno",
            "prediction_cutoff_ts",
            "target__Si_mean",
            "target__Si_sample_count",
        ]
    ].rename(columns={"target__Si_mean": "actual__Si_mean"})
    curve = recent.merge(
        predictions,
        on=["official_meltno", "prediction_cutoff_ts"],
        how="inner",
        validate="one_to_one",
    ).sort_values(["prediction_cutoff_ts", "official_meltno"], kind="stable")
    curve["absolute_error"] = (
        curve["prediction__Si_mean"] - curve["actual__Si_mean"]
    ).abs()
    prospective = curve.loc[
        curve["prediction_cutoff_ts"] >= PROSPECTIVE_BOUNDARY
    ].copy()
    metrics_path = output_dir / "metrics.json"
    metrics = (
        json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics_path.is_file()
        else {}
    )
    metrics.update(
        {
            "status": "experimental_offline_readonly_corrected_residual_reconstruction",
            "all_latest_15_days": regression_metrics(curve),
            "strictly_after_2026_07_27": (
                regression_metrics(prospective) if len(prospective) >= 2 else None
            ),
            "model_weights": joblib.load(args.model.resolve())["weights"],
            "feature_audit": feature_audit,
            "prediction_reconstruction": (
                "thermal_xgb/lgbm_huber7/lgbm_huber15_decay90 are residuals; "
                "published prior-heat mean-Si baseline is added before weighting"
            ),
        }
    )
    curve.to_csv(
        output_dir / "si_average_actual_vs_prediction.csv",
        index=False,
        encoding="utf-8-sig",
    )
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    render_curve(curve, output_dir / "si_average_actual_vs_prediction.png")
    print(
        json.dumps(
            {
                "ok": True,
                "curve_rows": len(curve),
                "metrics": metrics["strictly_after_2026_07_27"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
