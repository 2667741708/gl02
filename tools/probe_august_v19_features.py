"""Probe whether July-trained/August-holdout V19 feature columns align."""
from pathlib import Path
import pandas as pd
from si_semantic_engine.prospective import build_inference_feature_frame


def main() -> None:
    root = Path(r"PT/预测铁水Si含量")
    formal = root / "data/processed/formal_v3_historyfix_r12_20260727"
    recent = root / "reports/experiments/EXP-SI-AVERAGE-CURVE-22012-001_20260806"
    rows = pd.read_csv(recent / "inputs/prediction_rows.csv", low_memory=False)
    targets = pd.concat([
        pd.read_csv(formal / "formal_heat_targets.csv", low_memory=False),
        pd.read_csv(recent / "inputs/heat_targets_mean.csv", low_memory=False),
    ], ignore_index=True).drop_duplicates("official_meltno", keep="last")
    samples = pd.concat([
        pd.read_csv(formal / "formal_samples.csv", low_memory=False),
        pd.read_csv(recent / "inputs/formal_samples.csv", low_memory=False),
    ], ignore_index=True)
    features, audit = build_inference_feature_frame(
        rows, targets, samples,
        root.parent / "高炉3D模型/docs/GL02传感器点位清单.v1.json",
        recent / "temporal_stats",
    )
    print({"rows": len(features), "columns": len(features.columns), "first": features.columns[:10].tolist(), "audit": audit})
    features.to_csv(recent / "inputs/august_v19_inference_features.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
