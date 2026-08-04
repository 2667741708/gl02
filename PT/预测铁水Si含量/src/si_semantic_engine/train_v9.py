"""Blend tree, boosted-residual and history components across time folds.

The V9 simplex ensemble searches non-negative weights on five independently
trained components.  Selection uses April, May and June only; July remains
the historical post-selection evaluation.

Requirement:
    REQ-SI-MULTIMODEL-ENSEMBLE-V9-20260727
"""

from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Sequence

import joblib
import lightgbm
import numpy as np
import pandas as pd
import sklearn
import xgboost

from .formal_dataset import sha256_file
from .train_v3 import TARGET
from .train_v6 import (
    _artifact_hashes,
    _temperature_label_audit,
    _write_json,
    metrics,
)
from .train_v7 import _assemble_features, _component_predictions
from .train_v8 import LgbmSpec, _feature_args, _fit_predict


REQUIREMENT_ID = "REQ-SI-MULTIMODEL-ENSEMBLE-V9-20260727"
COMPONENT_NAMES = (
    "direct",
    "thermal_xgb",
    "lgbm_huber7",
    "lgbm_huber15_decay90",
    "history",
)
LGBM_SPECS = {
    "lgbm_huber7": LgbmSpec(
        "huber_leaf7_residual", "huber", 7, 35, "residual"
    ),
    "lgbm_huber15_decay90": LgbmSpec(
        "huber_leaf15_residual_decay90",
        "huber",
        15,
        45,
        "residual",
        90.0,
    ),
}


def _component_bundle(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    evaluation_mask: pd.Series,
    *,
    feature_args: dict[str, Sequence[str]],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    base_components, audit = _component_predictions(
        combined,
        train_mask,
        evaluation_mask,
        **feature_args,
    )
    train = combined.loc[train_mask]
    evaluation = combined.loc[evaluation_mask]
    thermal_features = audit["thermal_features"]
    components = {
        "direct": base_components["direct"],
        "thermal_xgb": base_components["thermal"],
        "history": base_components["history"],
    }
    lgbm_models: dict[str, Any] = {}
    for name, spec in LGBM_SPECS.items():
        model, prediction, _ = _fit_predict(
            spec, train, evaluation, thermal_features
        )
        lgbm_models[name] = model
        components[name] = prediction
    audit["lgbm_models"] = lgbm_models
    return components, audit


def _simplex_weights(units: int = 10) -> list[dict[str, float]]:
    output: list[dict[str, float]] = []
    for values in product(range(units + 1), repeat=len(COMPONENT_NAMES) - 1):
        used = sum(values)
        if used > units:
            continue
        completed = (*values, units - used)
        output.append(
            {
                name: value / float(units)
                for name, value in zip(COMPONENT_NAMES, completed)
            }
        )
    return output


def _blend(
    components: dict[str, np.ndarray],
    weights: dict[str, float],
) -> np.ndarray:
    return sum(
        weights[name] * np.asarray(components[name], dtype=float)
        for name in COMPONENT_NAMES
    )


def _rank_weights(
    folds: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for weights in _simplex_weights():
        fold_metrics: dict[str, dict[str, float]] = {}
        for name, fold in folds.items():
            fold_metrics[name] = metrics(
                fold["actual"], _blend(fold["components"], weights)
            )
        maes = np.asarray(
            [item["mae"] for item in fold_metrics.values()], dtype=float
        )
        hits = np.asarray(
            [
                item["hit_rate_abs_le_002"]
                for item in fold_metrics.values()
            ],
            dtype=float,
        )
        candidates.append(
            {
                "weights": weights,
                "folds": fold_metrics,
                "mean_mae": float(np.mean(maes)),
                "std_mae": float(np.std(maes, ddof=0)),
                "max_fold_mae": float(np.max(maes)),
                "mean_hit_rate_abs_le_002": float(np.mean(hits)),
                "robust_mae_score": float(
                    np.mean(maes) + 0.50 * np.std(maes, ddof=0)
                ),
            }
        )
    return sorted(
        candidates,
        key=lambda item: (
            item["robust_mae_score"],
            item["max_fold_mae"],
            -item["mean_hit_rate_abs_le_002"],
            tuple(item["weights"][name] for name in COMPONENT_NAMES),
        ),
    )


def run_experiment(
    *,
    dataset_path: Path,
    heat_targets_path: Path,
    samples_path: Path,
    catalog_path: Path,
    temporal_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    models_dir = output_dir / "models"
    models_dir.mkdir(exist_ok=True)
    combined, blocks = _assemble_features(
        dataset_path=dataset_path,
        heat_targets_path=heat_targets_path,
        samples_path=samples_path,
        catalog_path=catalog_path,
        temporal_dir=temporal_dir,
    )
    feature_args = dict(_feature_args(blocks))
    fold_masks = {
        "2026-04": (
            combined["prediction_month"].lt("2026-04"),
            combined["prediction_month"].eq("2026-04"),
        ),
        "2026-05": (
            combined["prediction_month"].lt("2026-05"),
            combined["prediction_month"].eq("2026-05"),
        ),
        "2026-06_fixed_validation": (
            combined["experiment_split"].eq("train"),
            combined["experiment_split"].eq("validation"),
        ),
    }
    folds: dict[str, dict[str, Any]] = {}
    fold_audit: dict[str, Any] = {}
    for name, (train_mask, evaluation_mask) in fold_masks.items():
        components, audit = _component_bundle(
            combined,
            train_mask,
            evaluation_mask,
            feature_args=feature_args,
        )
        folds[name] = {
            "components": components,
            "actual": combined.loc[
                evaluation_mask, TARGET
            ].to_numpy(float),
        }
        fold_audit[name] = {
            "train_rows": int(train_mask.sum()),
            "evaluation_rows": int(evaluation_mask.sum()),
            "direct_feature_count": len(audit["direct_features"]),
            "thermal_feature_count": len(audit["thermal_features"]),
        }
    weight_ranking = _rank_weights(folds)
    best_score = weight_ranking[0]["robust_mae_score"]
    pareto_pool = [
        item
        for item in weight_ranking
        if item["robust_mae_score"] <= best_score + 0.0002
    ]
    selected = min(
        pareto_pool,
        key=lambda item: (
            -item["mean_hit_rate_abs_le_002"],
            item["robust_mae_score"],
            item["max_fold_mae"],
        ),
    )

    train_mask = combined["experiment_split"].eq("train")
    test_mask = combined["experiment_split"].eq("test")
    test_components, audit = _component_bundle(
        combined,
        train_mask,
        test_mask,
        feature_args=feature_args,
    )
    test = combined.loc[test_mask].copy()
    prediction = _blend(test_components, selected["weights"])
    test_metrics = metrics(test[TARGET].to_numpy(float), prediction)
    component_metrics = {
        name: metrics(test[TARGET].to_numpy(float), values)
        for name, values in test_components.items()
    }
    predictions = test[
        ["official_meltno", "prediction_cutoff_ts", TARGET]
    ].copy()
    for name, values in test_components.items():
        predictions[f"prediction__{name}"] = values
    predictions["prediction__Si_ensemble"] = prediction
    predictions["absolute_error"] = np.abs(
        predictions[TARGET] - prediction
    )
    predictions.to_csv(
        output_dir / "predictions_test.csv",
        index=False,
        encoding="utf-8-sig",
    )
    joblib.dump(
        {
            "direct_model": audit["direct_model"],
            "thermal_model": audit["thermal_model"],
            "lgbm_models": audit["lgbm_models"],
            "direct_features": audit["direct_features"],
            "thermal_features": audit["thermal_features"],
            "fallback": audit["fallback"],
            "weights": selected["weights"],
            "status": "experimental_offline_v9",
        },
        models_dir / "selected_v9_ensemble.joblib",
    )
    temperature_audit = _temperature_label_audit(
        combined, blocks["heat_targets"]
    )
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v9",
        "selection_contract": (
            "five-component simplex weights selected on April/May expanding "
            "folds plus fixed June validation; within 0.0002 robust-MAE "
            "Pareto pool maximize mean ±0.02 hit; July read afterwards"
        ),
        "selected": {
            **selected,
            "historical_test": test_metrics,
            "historical_test_components": component_metrics,
        },
        "weight_ranking_top100": weight_ranking[:100],
        "pareto_pool_size": len(pareto_pool),
        "pretest_fold_audit": fold_audit,
        "joint_task_readiness": {
            "si_point_head": "trained_experimental_offline_v9",
            **temperature_audit,
        },
        "goal": {
            "mae_target": 0.02,
            "tolerance_target": 0.02,
            "status": (
                "reached" if test_metrics["mae"] <= 0.02 else "not_reached"
            ),
        },
    }
    _write_json(output_dir / "metrics.json", result)
    _write_json(
        output_dir / "feature_contract.json",
        {
            "windows_minutes": blocks["windows_minutes"],
            "v4_derivation": blocks["v4_audit"],
            "temporal_pivot": blocks["temporal_audit"],
            "chemistry_history": blocks["chemistry_audit"],
            "direct_feature_count": len(audit["direct_features"]),
            "thermal_feature_count": len(audit["thermal_features"]),
            "all_features_strictly_before_cutoff": True,
            "taphole_temperature_is_proxy_only": True,
            "cooling_wall_heat_loss_status": (
                "not_in_current_133_point_catalog"
            ),
        },
    )
    report = [
        "# V9 多模型Pareto集成报告",
        "",
        f"- 预测试稳健分数：{selected['robust_mae_score']:.6f}",
        f"- 预测试平均±0.02命中率：{selected['mean_hit_rate_abs_le_002']:.2%}",
        f"- 权重：`{json.dumps(selected['weights'], ensure_ascii=False)}`",
        (
            f"- 历史7月 MAE / ±0.02 / ±0.05："
            f"{test_metrics['mae']:.6f} / "
            f"{test_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        "",
        "- 真实铁水温度标签仍为0行，温度头未训练。",
        "- 未达到0.02目标前保持离线实验状态，禁止接生产MCP。",
        "",
    ]
    (output_dir / "report.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    manifest = {
        "requirement_id": REQUIREMENT_ID,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "runtime": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "xgboost": xgboost.__version__,
            "lightgbm": lightgbm.__version__,
        },
        "inputs": {
            "dataset": sha256_file(dataset_path),
            "heat_targets": sha256_file(heat_targets_path),
            "samples": sha256_file(samples_path),
            "sensor_catalog": sha256_file(catalog_path),
            "temporal_manifest": sha256_file(
                temporal_dir / "manifest.json"
            ),
        },
        "artifacts": _artifact_hashes(output_dir),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_json(output_dir / "sha256sums.json", _artifact_hashes(output_dir))
    return result


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="训练V9多模型Pareto集成。"
    )
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--heat-targets", type=Path, required=True)
    cli.add_argument("--samples", type=Path, required=True)
    cli.add_argument("--sensor-catalog", type=Path, required=True)
    cli.add_argument("--temporal-dir", type=Path, required=True)
    cli.add_argument("--output-dir", type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result = run_experiment(
        dataset_path=args.dataset,
        heat_targets_path=args.heat_targets,
        samples_path=args.samples,
        catalog_path=args.sensor_catalog,
        temporal_dir=args.temporal_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(result["selected"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
