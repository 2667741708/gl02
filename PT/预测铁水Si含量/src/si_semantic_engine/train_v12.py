"""Blend direct, thermal and lag-field experts with train-only weights.

Requirement:
    REQ-SI-LAG-FIELD-ENSEMBLE-V12-20260727
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
from .train_v7 import _component_predictions
from .train_v8 import LgbmSpec, _feature_args, _fit_predict, _fold_definitions
from .train_v10 import _assemble_v10_features, _v10_recipes


REQUIREMENT_ID = "REQ-SI-LAG-FIELD-ENSEMBLE-V12-20260727"
COMPONENT_NAMES = (
    "direct",
    "thermal_xgb",
    "lgbm_thermal",
    "lgbm_lag_field",
)
LGBM_SPEC = LgbmSpec(
    "huber_leaf7_residual", "huber", 7, 35, "residual"
)


def simplex_weights(units: int = 20) -> list[dict[str, float]]:
    """Enumerate non-negative four-component weights that sum to one."""

    output: list[dict[str, float]] = []
    for values in product(range(units + 1), repeat=3):
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
    components: dict[str, np.ndarray], weights: dict[str, float]
) -> np.ndarray:
    return sum(
        float(weights[name]) * np.asarray(components[name], dtype=float)
        for name in COMPONENT_NAMES
    )


def _component_bundle(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    evaluation_mask: pd.Series,
    *,
    feature_args: dict[str, Sequence[str]],
    lag_field_features: Sequence[str],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    base, audit = _component_predictions(
        combined,
        train_mask,
        evaluation_mask,
        **feature_args,
    )
    train = combined.loc[train_mask]
    evaluation = combined.loc[evaluation_mask]
    thermal_model, thermal_lgbm, _ = _fit_predict(
        LGBM_SPEC, train, evaluation, audit["thermal_features"]
    )
    lag_model, lag_prediction, _ = _fit_predict(
        LGBM_SPEC, train, evaluation, lag_field_features
    )
    return {
        "direct": base["direct"],
        "thermal_xgb": base["thermal"],
        "lgbm_thermal": thermal_lgbm,
        "lgbm_lag_field": lag_prediction,
    }, {
        **audit,
        "lgbm_thermal_model": thermal_model,
        "lgbm_lag_field_model": lag_model,
        "lag_field_features": list(lag_field_features),
    }


def _rank_weights(
    folds: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    ranking: list[dict[str, Any]] = []
    for weights in simplex_weights():
        fold_metrics = {
            name: metrics(
                fold["actual"], _blend(fold["components"], weights)
            )
            for name, fold in folds.items()
        }
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
        ranking.append(
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
        ranking,
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
    combined, blocks = _assemble_v10_features(
        dataset_path=dataset_path,
        heat_targets_path=heat_targets_path,
        samples_path=samples_path,
        catalog_path=catalog_path,
        temporal_dir=temporal_dir,
    )
    feature_args = dict(_feature_args(blocks))
    fold_masks = _fold_definitions(combined)
    folds: dict[str, dict[str, Any]] = {}
    fold_audit: dict[str, Any] = {}
    for fold_name, (train_mask, evaluation_mask) in fold_masks.items():
        recipes, recipe_audit = _v10_recipes(
            combined, train_mask, blocks
        )
        components, audit = _component_bundle(
            combined,
            train_mask,
            evaluation_mask,
            feature_args=feature_args,
            lag_field_features=recipes[
                "v10_hybrid_importance250"
            ],
        )
        folds[fold_name] = {
            "components": components,
            "actual": combined.loc[
                evaluation_mask, TARGET
            ].to_numpy(float),
        }
        fold_audit[fold_name] = {
            "train_rows": int(train_mask.sum()),
            "evaluation_rows": int(evaluation_mask.sum()),
            "direct_feature_count": len(audit["direct_features"]),
            "thermal_feature_count": len(audit["thermal_features"]),
            "lag_field_feature_count": len(
                audit["lag_field_features"]
            ),
            "recipe_selection": recipe_audit,
        }
        print(
            json.dumps(
                {"stage": "fold_complete", "fold": fold_name},
                ensure_ascii=False,
            ),
            flush=True,
        )
    weight_ranking = _rank_weights(folds)
    best_score = weight_ranking[0]["robust_mae_score"]
    pareto_pool = [
        item
        for item in weight_ranking
        if item["robust_mae_score"] <= best_score + 0.00015
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
    final_recipes, final_recipe_audit = _v10_recipes(
        combined, train_mask, blocks
    )
    test_components, audit = _component_bundle(
        combined,
        train_mask,
        test_mask,
        feature_args=feature_args,
        lag_field_features=final_recipes[
            "v10_hybrid_importance250"
        ],
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
            "thermal_xgb_model": audit["thermal_model"],
            "lgbm_thermal_model": audit["lgbm_thermal_model"],
            "lgbm_lag_field_model": audit["lgbm_lag_field_model"],
            "direct_features": audit["direct_features"],
            "thermal_features": audit["thermal_features"],
            "lag_field_features": audit["lag_field_features"],
            "fallback": audit["fallback"],
            "weights": selected["weights"],
            "status": "experimental_offline_v12",
        },
        models_dir / "selected_v12_ensemble.joblib",
    )
    temperature_audit = _temperature_label_audit(
        combined, blocks["heat_targets"]
    )
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v12",
        "selection_contract": (
            "four-component 0.05 simplex weights selected on April/May "
            "expanding folds plus fixed June validation; lag-field ranking "
            "rebuilt inside every fold; July is historical comparison only"
        ),
        "selected": {
            **selected,
            "historical_test": test_metrics,
            "historical_test_components": component_metrics,
        },
        "weight_ranking_top200": weight_ranking[:200],
        "pareto_pool_size": len(pareto_pool),
        "fold_audit": fold_audit,
        "joint_task_readiness": {
            "si_point_head": "trained_experimental_offline_v12",
            **temperature_audit,
        },
        "goal": {
            "mae_target": 0.02,
            "status": (
                "reached" if test_metrics["mae"] <= 0.02 else "not_reached"
            ),
        },
    }
    _write_json(output_dir / "metrics.json", result)
    _write_json(
        output_dir / "selection_audit.json",
        {"folds": fold_audit, "final_train": final_recipe_audit},
    )
    _write_json(
        output_dir / "feature_contract.json",
        {
            "components": list(COMPONENT_NAMES),
            "weights": selected["weights"],
            "weight_step": 0.05,
            "all_feature_selection_training_fold_only": True,
            "all_sensor_features_strictly_before_cutoff": True,
            "taphole_temperature_is_proxy_only": True,
        },
    )
    report = [
        "# V12 热状态与时延场专家集成实验",
        "",
        f"- 跨月稳健分数：{selected['robust_mae_score']:.6f}",
        f"- 平均±0.02命中率：{selected['mean_hit_rate_abs_le_002']:.2%}",
        f"- 权重：`{json.dumps(selected['weights'], ensure_ascii=False)}`",
        (
            f"- 历史7月 MAE / ±0.02 / ±0.05："
            f"{test_metrics['mae']:.6f} / "
            f"{test_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        "",
        "- 七月为历史对照，不是新盲测。",
        "- 温度联合头因真实铁水温度标签缺失继续阻止。",
        "- 未达到0.02目标，保持离线实验状态。",
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
        description="训练V12热状态与时延场专家集成。"
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

