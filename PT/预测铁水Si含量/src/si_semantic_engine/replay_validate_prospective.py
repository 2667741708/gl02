"""Replay frozen prospective inference against immutable experiment outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .prospective import (
    build_inference_feature_frame,
    load_frozen_models,
    predict_frozen_candidates,
)


def run_validation(
    *,
    dataset_path: Path,
    heat_targets_path: Path,
    samples_path: Path,
    catalog_path: Path,
    temporal_dir: Path,
    protocol_path: Path,
    expected_v9_path: Path,
    expected_v10_path: Path,
    expected_v13_path: Path | None = None,
) -> dict:
    dataset = pd.read_csv(
        dataset_path, low_memory=False, encoding="utf-8-sig"
    )
    heat_targets = pd.read_csv(
        heat_targets_path, low_memory=False, encoding="utf-8-sig"
    )
    samples = pd.read_csv(
        samples_path, low_memory=False, encoding="utf-8-sig"
    )
    replay_rows = dataset.loc[
        dataset["experiment_split"].eq("test")
    ].copy()
    features, audit = build_inference_feature_frame(
        replay_rows,
        heat_targets,
        samples,
        catalog_path,
        temporal_dir,
    )
    protocol, bundles = load_frozen_models(protocol_path)
    predictions = predict_frozen_candidates(features, protocol, bundles)
    expected_v9 = pd.read_csv(
        expected_v9_path, low_memory=False, encoding="utf-8-sig"
    )
    expected_v10 = pd.read_csv(
        expected_v10_path, low_memory=False, encoding="utf-8-sig"
    )
    expected_v13 = (
        pd.read_csv(
            expected_v13_path,
            low_memory=False,
            encoding="utf-8-sig",
        )
        if expected_v13_path is not None
        else None
    )
    comparison = predictions[
        [
            "official_meltno",
            "prediction__v9_point",
            "prediction__v9_direct",
            "prediction__v9_thermal_xgb",
            "prediction__v9_lgbm_huber7",
            "prediction__v9_lgbm_huber15_decay90",
            "prediction__v9_history",
            "prediction__v10_point",
        ]
    ].merge(
        expected_v9[
            [
                "official_meltno",
                "prediction__direct",
                "prediction__thermal_xgb",
                "prediction__lgbm_huber7",
                "prediction__lgbm_huber15_decay90",
                "prediction__history",
                "prediction__Si_ensemble",
            ]
        ],
        on="official_meltno",
        how="inner",
        validate="one_to_one",
    ).merge(
        expected_v10[
            ["official_meltno", "prediction__Si_representative"]
        ],
        on="official_meltno",
        how="inner",
        validate="one_to_one",
    )
    if len(comparison) != len(predictions):
        raise RuntimeError("回放预测与期望实验炉次集合不一致")
    v9_difference = np.abs(
        comparison["prediction__v9_point"]
        - comparison["prediction__Si_ensemble"]
    )
    v10_difference = np.abs(
        comparison["prediction__v10_point"]
        - comparison["prediction__Si_representative"]
    )
    component_differences = {
        name: float(
            np.abs(
                comparison[f"prediction__v9_{name}"]
                - comparison[f"prediction__{name}"]
            ).max()
        )
        for name in (
            "direct",
            "thermal_xgb",
            "lgbm_huber7",
            "lgbm_huber15_decay90",
            "history",
        )
    }
    result = {
        "status": "passed",
        "rows": len(comparison),
        "input_target_columns_removed": audit["target_columns_removed"],
        "current_heat_target_used": audit["current_heat_target_used"],
        "v9_max_absolute_prediction_difference": float(
            v9_difference.max()
        ),
        "v10_max_absolute_prediction_difference": float(
            v10_difference.max()
        ),
        "v9_component_max_absolute_differences": component_differences,
        "tolerance": 1e-10,
    }
    if expected_v13 is not None:
        v13_comparison = predictions[
            ["official_meltno", "prediction__v13_point"]
        ].merge(
            expected_v13[
                [
                    "official_meltno",
                    "prediction__Si_representative",
                ]
            ],
            on="official_meltno",
            how="inner",
            validate="one_to_one",
        )
        if len(v13_comparison) != len(predictions):
            raise RuntimeError("V13回放预测与期望炉次集合不一致")
        result["v13_max_absolute_prediction_difference"] = float(
            np.abs(
                v13_comparison["prediction__v13_point"]
                - v13_comparison[
                    "prediction__Si_representative"
                ]
            ).max()
        )
    if (
        result["v9_max_absolute_prediction_difference"]
        > result["tolerance"]
        or result["v10_max_absolute_prediction_difference"]
        > result["tolerance"]
        or result.get(
            "v13_max_absolute_prediction_difference", 0.0
        )
        > result["tolerance"]
    ):
        result["status"] = "failed_prediction_mismatch"
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="删除当前炉标签后回放V9/V10冻结模型。"
    )
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--heat-targets", type=Path, required=True)
    cli.add_argument("--samples", type=Path, required=True)
    cli.add_argument("--sensor-catalog", type=Path, required=True)
    cli.add_argument("--temporal-dir", type=Path, required=True)
    cli.add_argument("--protocol", type=Path, required=True)
    cli.add_argument("--expected-v9", type=Path, required=True)
    cli.add_argument("--expected-v10", type=Path, required=True)
    cli.add_argument("--expected-v13", type=Path)
    cli.add_argument("--output", type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result = run_validation(
        dataset_path=args.dataset,
        heat_targets_path=args.heat_targets,
        samples_path=args.samples,
        catalog_path=args.sensor_catalog,
        temporal_dir=args.temporal_dir,
        protocol_path=args.protocol,
        expected_v9_path=args.expected_v9,
        expected_v10_path=args.expected_v10,
        expected_v13_path=args.expected_v13,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
