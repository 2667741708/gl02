"""Evaluate LightGBM robust-loss models for the V6 feature contract.

Every candidate is evaluated on April, May and the fixed June validation
without reading the historical July test.  Feature ranking is rebuilt inside
each fold.  July is evaluated once after the robust candidate is selected.

Requirement:
    REQ-SI-LGBM-ROBUST-V8-20260727
"""

from __future__ import annotations

import argparse
import json
import platform
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import joblib
import lightgbm
import numpy as np
import pandas as pd
import sklearn
from lightgbm import LGBMRegressor

from .formal_dataset import sha256_file
from .train_v3 import TARGET
from .train_v6 import (
    _artifact_hashes,
    _feature_recipes,
    _history_baseline,
    _recency_weights,
    _temperature_label_audit,
    _write_json,
    metrics,
)
from .train_v7 import _assemble_features


REQUIREMENT_ID = "REQ-SI-LGBM-ROBUST-V8-20260727"
RANDOM_STATE = 20260727


@dataclass(frozen=True)
class LgbmSpec:
    name: str
    objective: str
    num_leaves: int
    min_child_samples: int
    target_mode: str
    recency_half_life_days: float | None = None
    learning_rate: float = 0.025
    n_estimators: int = 550


def _specs() -> list[LgbmSpec]:
    return [
        LgbmSpec("l1_leaf7_direct", "regression_l1", 7, 35, "direct"),
        LgbmSpec("l1_leaf7_residual", "regression_l1", 7, 35, "residual"),
        LgbmSpec(
            "l1_leaf7_residual_decay90",
            "regression_l1",
            7,
            35,
            "residual",
            90.0,
        ),
        LgbmSpec(
            "l1_leaf7_residual_decay45",
            "regression_l1",
            7,
            35,
            "residual",
            45.0,
        ),
        LgbmSpec("l1_leaf15_residual", "regression_l1", 15, 45, "residual"),
        LgbmSpec(
            "l1_leaf15_residual_decay90",
            "regression_l1",
            15,
            45,
            "residual",
            90.0,
        ),
        LgbmSpec("huber_leaf7_direct", "huber", 7, 35, "direct"),
        LgbmSpec("huber_leaf7_residual", "huber", 7, 35, "residual"),
        LgbmSpec(
            "huber_leaf7_residual_decay90",
            "huber",
            7,
            35,
            "residual",
            90.0,
        ),
        LgbmSpec(
            "huber_leaf15_residual_decay90",
            "huber",
            15,
            45,
            "residual",
            90.0,
        ),
    ]


def _model(spec: LgbmSpec, *, objective: str | None = None) -> LGBMRegressor:
    return LGBMRegressor(
        objective=objective or spec.objective,
        n_estimators=spec.n_estimators,
        learning_rate=spec.learning_rate,
        num_leaves=spec.num_leaves,
        max_depth=-1,
        min_child_samples=spec.min_child_samples,
        subsample=0.85,
        subsample_freq=1,
        colsample_bytree=0.60,
        reg_alpha=0.10,
        reg_lambda=8.0,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbosity=-1,
    )


def _fit_predict(
    spec: LgbmSpec,
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    features: Sequence[str],
) -> tuple[LGBMRegressor, np.ndarray, float]:
    fallback = float(train[TARGET].median())
    train_baseline = _history_baseline(train, fallback=fallback)
    evaluation_baseline = _history_baseline(
        evaluation, fallback=fallback
    )
    target = train[TARGET].to_numpy(float)
    if spec.target_mode == "residual":
        target = target - train_baseline.to_numpy(float)
    model = _model(spec)
    weights = _recency_weights(
        train["prediction_cutoff_ts"], spec.recency_half_life_days
    )
    model.fit(
        train[list(features)],
        target,
        sample_weight=weights,
        categorical_feature="auto",
    )
    prediction = model.predict(evaluation[list(features)])
    if spec.target_mode == "residual":
        prediction = prediction + evaluation_baseline.to_numpy(float)
    return model, np.asarray(prediction, dtype=float), fallback


def _feature_args(blocks: dict[str, Any]) -> dict[str, Sequence[str]]:
    return {
        "base_history": blocks["base_history"],
        "temporal_columns": blocks["temporal_columns"],
        "multiscale_columns": blocks["multiscale_columns"],
        "heat_state_columns": blocks["heat_state_columns"],
        "spatial_columns": blocks["spatial_columns"],
        "chemistry_columns": blocks["chemistry_columns"],
    }


def _fold_definitions(
    combined: pd.DataFrame,
) -> dict[str, tuple[pd.Series, pd.Series]]:
    return {
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


def _robust_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["robust_mae_score"],
        item["max_fold_mae"],
        -item["mean_hit_rate_abs_le_002"],
        item["candidate"],
    )


def _quantile_distribution(
    spec: LgbmSpec,
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: Sequence[str],
) -> tuple[np.ndarray, dict[str, LGBMRegressor]]:
    fallback = float(train[TARGET].median())
    train_baseline = _history_baseline(train, fallback=fallback)
    test_baseline = _history_baseline(test, fallback=fallback)
    target = train[TARGET].to_numpy(float)
    if spec.target_mode == "residual":
        target = target - train_baseline.to_numpy(float)
    predictions: list[np.ndarray] = []
    models: dict[str, LGBMRegressor] = {}
    for quantile in (0.10, 0.50, 0.90):
        model = LGBMRegressor(
            objective="quantile",
            alpha=quantile,
            n_estimators=spec.n_estimators,
            learning_rate=spec.learning_rate,
            num_leaves=spec.num_leaves,
            min_child_samples=spec.min_child_samples,
            subsample=0.85,
            subsample_freq=1,
            colsample_bytree=0.60,
            reg_alpha=0.10,
            reg_lambda=8.0,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbosity=-1,
        )
        weights = _recency_weights(
            train["prediction_cutoff_ts"],
            spec.recency_half_life_days,
        )
        model.fit(train[list(features)], target, sample_weight=weights)
        prediction = model.predict(test[list(features)])
        if spec.target_mode == "residual":
            prediction = prediction + test_baseline.to_numpy(float)
        predictions.append(np.asarray(prediction, dtype=float))
        models[f"p{int(quantile * 100):02d}"] = model
    return np.sort(np.vstack(predictions), axis=0), models


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
    feature_args = _feature_args(blocks)
    recipes_by_fold: dict[str, dict[str, list[str]]] = {}
    fold_masks = _fold_definitions(combined)
    for name, (train_mask, _) in fold_masks.items():
        recipes_by_fold[name], _ = _feature_recipes(
            combined, train_mask, **feature_args
        )
    recipe_names = (
        "base_history",
        "base_importance250",
        "base_plus_chemistry",
        "base_chemistry_heat250",
    )
    candidates: list[dict[str, Any]] = []
    for recipe_name in recipe_names:
        for spec in _specs():
            folds: dict[str, dict[str, float]] = {}
            for fold_name, (train_mask, evaluation_mask) in (
                fold_masks.items()
            ):
                train = combined.loc[train_mask]
                evaluation = combined.loc[evaluation_mask]
                features = recipes_by_fold[fold_name][recipe_name]
                model, prediction, _ = _fit_predict(
                    spec, train, evaluation, features
                )
                del model
                folds[fold_name] = metrics(
                    evaluation[TARGET].to_numpy(float), prediction
                )
            maes = np.asarray(
                [item["mae"] for item in folds.values()], dtype=float
            )
            hits = np.asarray(
                [
                    item["hit_rate_abs_le_002"]
                    for item in folds.values()
                ],
                dtype=float,
            )
            candidates.append(
                {
                    "candidate": f"{recipe_name}__{spec.name}",
                    "recipe": recipe_name,
                    "spec": spec.__dict__,
                    "folds": folds,
                    "mean_mae": float(np.mean(maes)),
                    "std_mae": float(np.std(maes, ddof=0)),
                    "max_fold_mae": float(np.max(maes)),
                    "mean_hit_rate_abs_le_002": float(np.mean(hits)),
                    "robust_mae_score": float(
                        np.mean(maes)
                        + 0.50 * np.std(maes, ddof=0)
                    ),
                }
            )
    ranking = sorted(candidates, key=_robust_key)
    best_robust_score = ranking[0]["robust_mae_score"]
    pareto_pool = [
        item
        for item in ranking
        if item["robust_mae_score"] <= best_robust_score + 0.0001
    ]
    selected = min(
        pareto_pool,
        key=lambda item: (
            -item["mean_hit_rate_abs_le_002"],
            item["robust_mae_score"],
            item["max_fold_mae"],
            item["candidate"],
        ),
    )
    selected_spec = LgbmSpec(**selected["spec"])

    train_mask = combined["experiment_split"].eq("train")
    test_mask = combined["experiment_split"].eq("test")
    train = combined.loc[train_mask]
    test = combined.loc[test_mask].copy()
    final_recipes, selection_audit = _feature_recipes(
        combined, train_mask, **feature_args
    )
    selected_features = final_recipes[selected["recipe"]]
    model, prediction, fallback = _fit_predict(
        selected_spec, train, test, selected_features
    )
    test_metrics = metrics(test[TARGET].to_numpy(float), prediction)
    distribution, distribution_models = _quantile_distribution(
        selected_spec, train, test, selected_features
    )
    p10, p50, p90 = distribution
    distribution_metrics = {
        "p50": metrics(test[TARGET].to_numpy(float), p50),
        "p10_p90_coverage": float(
            np.mean(
                (test[TARGET].to_numpy(float) >= p10)
                & (test[TARGET].to_numpy(float) <= p90)
            )
        ),
        "mean_p10_p90_width": float(np.mean(p90 - p10)),
    }

    predictions = test[
        ["official_meltno", "prediction_cutoff_ts", TARGET]
    ].copy()
    predictions["prediction__Si_representative"] = prediction
    predictions["prediction__Si_p10"] = p10
    predictions["prediction__Si_p50"] = p50
    predictions["prediction__Si_p90"] = p90
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
            "model": model,
            "distribution_models": distribution_models,
            "features": selected_features,
            "spec": selected_spec,
            "fallback": fallback,
            "status": "experimental_offline_v8",
        },
        models_dir / "selected_v8.joblib",
    )
    importance = sorted(
        [
            {"feature": feature, "importance": float(value)}
            for feature, value in zip(
                selected_features, model.feature_importances_
            )
        ],
        key=lambda item: item["importance"],
        reverse=True,
    )
    _write_json(
        output_dir / "feature_importance.json", importance[:300]
    )
    temperature_audit = _temperature_label_audit(
        combined, blocks["heat_targets"]
    )
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v8",
        "selection_contract": (
            "all candidates selected by April/May expanding folds and fixed "
            "June validation; feature ranking rebuilt per fold; candidates "
            "within 0.0001 robust-MAE of the best form a Pareto pool and "
            "highest mean ±0.02 hit rate wins; historical July test read "
            "after selection"
        ),
        "pareto_policy": {
            "robust_mae_tolerance": 0.0001,
            "pool_size": len(pareto_pool),
            "secondary_objective": "mean_hit_rate_abs_le_002",
        },
        "selected": {
            **selected,
            "feature_count": len(selected_features),
            "historical_test": test_metrics,
            "distribution_test": distribution_metrics,
        },
        "candidate_ranking": ranking,
        "joint_task_readiness": {
            "si_distribution_head": "trained_experimental_offline_v8",
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
    _write_json(output_dir / "selection_audit.json", selection_audit)
    _write_json(
        output_dir / "feature_contract.json",
        {
            "selected_features": selected_features,
            "windows_minutes": blocks["windows_minutes"],
            "v4_derivation": blocks["v4_audit"],
            "temporal_pivot": blocks["temporal_audit"],
            "chemistry_history": blocks["chemistry_audit"],
            "all_features_strictly_before_cutoff": True,
            "taphole_temperature_is_proxy_only": True,
            "cooling_wall_heat_loss_status": (
                "not_in_current_133_point_catalog"
            ),
        },
    )
    report = [
        "# V8 LightGBM稳健损失实验报告",
        "",
        f"- 选中候选：`{selected['candidate']}`",
        (
            f"- 跨月稳健分数 / 平均MAE："
            f"{selected['robust_mae_score']:.6f} / "
            f"{selected['mean_mae']:.6f}"
        ),
        (
            f"- 历史7月 MAE / ±0.02 / ±0.05："
            f"{test_metrics['mae']:.6f} / "
            f"{test_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        (
            f"- 分布P50 MAE / P10-P90覆盖率："
            f"{distribution_metrics['p50']['mae']:.6f} / "
            f"{distribution_metrics['p10_p90_coverage']:.2%}"
        ),
        "",
        "- 真实铁水温度标签仍为0行，未训练温度或热状态概率头。",
        "- 历史7月已被多版本复用，仍需新炉次前瞻盲测。",
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
            "lightgbm": lightgbm.__version__,
            "random_state": RANDOM_STATE,
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
        description="训练V8 LightGBM稳健损失Si模型。"
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
