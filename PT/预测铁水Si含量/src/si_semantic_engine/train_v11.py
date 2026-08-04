"""Evaluate uncertainty-aware Si label surrogates and training weights.

The published target remains the formal heat representative median Si.
Alternative mean/median blends are training-only denoising surrogates; they
never enter inference features.

Requirement:
    REQ-SI-LABEL-RELIABILITY-V11-20260727
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

from .formal_dataset import sha256_file
from .train_v3 import TARGET
from .train_v6 import (
    _artifact_hashes,
    _history_baseline,
    _recency_weights,
    _temperature_label_audit,
    _write_json,
    metrics,
)
from .train_v8 import (
    LgbmSpec,
    _fold_definitions,
    _model,
    _quantile_distribution,
)
from .train_v10 import _assemble_v10_features, _v10_recipes


REQUIREMENT_ID = "REQ-SI-LABEL-RELIABILITY-V11-20260727"
MEAN_TARGET = "target__Si_mean"
STD_TARGET = "target__Si_std"
SAMPLE_COUNT_TARGET = "target__Si_sample_count"


@dataclass(frozen=True)
class LabelSpec:
    name: str
    mean_weight: float
    reliability_mode: str
    recency_half_life_days: float | None = None


def _label_specs() -> tuple[LabelSpec, ...]:
    return (
        LabelSpec("median_uniform", 0.0, "uniform"),
        LabelSpec("median_reliability", 0.0, "dispersion"),
        LabelSpec("blend25_uniform", 0.25, "uniform"),
        LabelSpec("blend25_reliability", 0.25, "dispersion"),
        LabelSpec(
            "blend25_reliability_decay90",
            0.25,
            "dispersion",
            90.0,
        ),
        LabelSpec("blend50_uniform", 0.50, "uniform"),
        LabelSpec("blend50_reliability", 0.50, "dispersion"),
        LabelSpec("mean_uniform", 1.0, "uniform"),
    )


def surrogate_target(
    frame: pd.DataFrame, mean_weight: float
) -> pd.Series:
    """Blend formal heat median and mean for training only."""

    if not 0.0 <= mean_weight <= 1.0:
        raise ValueError("mean_weight必须在0到1之间")
    median = pd.to_numeric(frame[TARGET], errors="raise")
    mean = pd.to_numeric(frame[MEAN_TARGET], errors="raise")
    return (1.0 - mean_weight) * median + mean_weight * mean


def label_reliability_weights(
    frame: pd.DataFrame, mode: str
) -> np.ndarray:
    """Weight repeatable multi-sample labels without creating features."""

    if mode == "uniform":
        return np.ones(len(frame), dtype=float)
    if mode != "dispersion":
        raise ValueError(f"未知标签可靠性模式：{mode}")
    count = pd.to_numeric(
        frame[SAMPLE_COUNT_TARGET], errors="coerce"
    ).clip(lower=1.0)
    deviation = pd.to_numeric(frame[STD_TARGET], errors="coerce")
    fallback = float(deviation.median(skipna=True))
    if not np.isfinite(fallback):
        fallback = 0.05
    deviation = deviation.fillna(fallback).clip(lower=0.0)
    repeatability = np.sqrt(count / 3.0)
    stability = 1.0 / (1.0 + (deviation / 0.05) ** 2)
    weights = (repeatability * stability).clip(lower=0.25, upper=2.0)
    mean_weight = float(weights.mean())
    if not np.isfinite(mean_weight) or mean_weight <= 0.0:
        raise ValueError("标签可靠性权重无效")
    return (weights / mean_weight).to_numpy(float)


def _fit_predict(
    label_spec: LabelSpec,
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    features: Sequence[str],
) -> tuple[Any, np.ndarray, float]:
    model_spec = LgbmSpec(
        name="huber_leaf7_residual",
        objective="huber",
        num_leaves=7,
        min_child_samples=35,
        target_mode="residual",
        recency_half_life_days=label_spec.recency_half_life_days,
    )
    fallback = float(train[TARGET].median())
    train_baseline = _history_baseline(train, fallback=fallback)
    evaluation_baseline = _history_baseline(
        evaluation, fallback=fallback
    )
    target = surrogate_target(
        train, label_spec.mean_weight
    ).to_numpy(float) - train_baseline.to_numpy(float)
    reliability = label_reliability_weights(
        train, label_spec.reliability_mode
    )
    recency = _recency_weights(
        train["prediction_cutoff_ts"],
        label_spec.recency_half_life_days,
    )
    sample_weight = (
        reliability if recency is None else reliability * recency
    )
    model = _model(model_spec)
    model.fit(
        train[list(features)],
        target,
        sample_weight=sample_weight,
        categorical_feature="auto",
    )
    prediction = (
        model.predict(evaluation[list(features)])
        + evaluation_baseline.to_numpy(float)
    )
    return model, np.asarray(prediction, dtype=float), fallback


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
    fold_masks = _fold_definitions(combined)
    recipes_by_fold: dict[str, dict[str, list[str]]] = {}
    audit_by_fold: dict[str, Any] = {}
    for fold_name, (train_mask, _) in fold_masks.items():
        recipes_by_fold[fold_name], audit_by_fold[fold_name] = (
            _v10_recipes(combined, train_mask, blocks)
        )
    recipe_names = ("v9_reference", "v10_hybrid_importance250")
    candidates: list[dict[str, Any]] = []
    for recipe_name in recipe_names:
        for label_spec in _label_specs():
            folds: dict[str, dict[str, float]] = {}
            for fold_name, (
                train_mask,
                evaluation_mask,
            ) in fold_masks.items():
                train = combined.loc[train_mask]
                evaluation = combined.loc[evaluation_mask]
                _, prediction, _ = _fit_predict(
                    label_spec,
                    train,
                    evaluation,
                    recipes_by_fold[fold_name][recipe_name],
                )
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
            candidate = {
                "candidate": f"{recipe_name}__{label_spec.name}",
                "recipe": recipe_name,
                "label_spec": label_spec.__dict__,
                "folds": folds,
                "mean_mae": float(np.mean(maes)),
                "std_mae": float(np.std(maes, ddof=0)),
                "max_fold_mae": float(np.max(maes)),
                "mean_hit_rate_abs_le_002": float(np.mean(hits)),
                "robust_mae_score": float(
                    np.mean(maes) + 0.50 * np.std(maes, ddof=0)
                ),
            }
            candidates.append(candidate)
            print(
                json.dumps(
                    {
                        "stage": "candidate_complete",
                        "candidate": candidate["candidate"],
                        "robust_mae_score": candidate[
                            "robust_mae_score"
                        ],
                        "mean_hit_rate_abs_le_002": candidate[
                            "mean_hit_rate_abs_le_002"
                        ],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    ranking = sorted(
        candidates,
        key=lambda item: (
            item["robust_mae_score"],
            item["max_fold_mae"],
            -item["mean_hit_rate_abs_le_002"],
            item["candidate"],
        ),
    )
    best_score = ranking[0]["robust_mae_score"]
    pareto_pool = [
        item
        for item in ranking
        if item["robust_mae_score"] <= best_score + 0.00015
    ]
    selected = min(
        pareto_pool,
        key=lambda item: (
            -item["mean_hit_rate_abs_le_002"],
            item["robust_mae_score"],
            item["candidate"],
        ),
    )
    selected_label_spec = LabelSpec(**selected["label_spec"])
    train_mask = combined["experiment_split"].eq("train")
    test_mask = combined["experiment_split"].eq("test")
    final_recipes, final_audit = _v10_recipes(
        combined, train_mask, blocks
    )
    selected_features = final_recipes[selected["recipe"]]
    train = combined.loc[train_mask]
    test = combined.loc[test_mask].copy()
    model, prediction, fallback = _fit_predict(
        selected_label_spec, train, test, selected_features
    )
    test_metrics = metrics(test[TARGET].to_numpy(float), prediction)
    # Distribution head continues to target the formal empirical quantiles,
    # not the training-only point surrogate.
    distribution_spec = LgbmSpec(
        "distribution_reference",
        "huber",
        7,
        35,
        "residual",
        selected_label_spec.recency_half_life_days,
    )
    distribution, distribution_models = _quantile_distribution(
        distribution_spec, train, test, selected_features
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
            "label_spec": selected_label_spec,
            "fallback": fallback,
            "status": "experimental_offline_v11",
        },
        models_dir / "selected_v11.joblib",
    )
    _write_json(
        output_dir / "feature_importance.json",
        sorted(
            [
                {"feature": feature, "importance": float(value)}
                for feature, value in zip(
                    selected_features, model.feature_importances_
                )
            ],
            key=lambda item: item["importance"],
            reverse=True,
        )[:500],
    )
    temperature_audit = _temperature_label_audit(
        combined, blocks["heat_targets"]
    )
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v11",
        "selection_contract": (
            "training-only median/mean surrogate and reliability weighting "
            "selected on April/May expanding folds plus fixed June "
            "validation; July is historical comparison only"
        ),
        "selected": {
            **selected,
            "feature_count": len(selected_features),
            "historical_test": test_metrics,
            "distribution_test": distribution_metrics,
        },
        "candidate_ranking": ranking,
        "joint_task_readiness": {
            "si_distribution_head": "trained_experimental_offline_v11",
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
        {"folds": audit_by_fold, "final_train": final_audit},
    )
    _write_json(
        output_dir / "feature_contract.json",
        {
            "published_target": TARGET,
            "training_surrogate": selected_label_spec.__dict__,
            "surrogate_is_never_an_inference_feature": True,
            "reliability_inputs": [
                SAMPLE_COUNT_TARGET,
                STD_TARGET,
            ],
            "selected_features": selected_features,
            "all_feature_selection_training_fold_only": True,
            "all_sensor_features_strictly_before_cutoff": True,
            "taphole_temperature_is_proxy_only": True,
        },
    )
    report = [
        "# V11 标签可靠性与训练目标平滑实验",
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
        "",
        "- 评价目标始终是正式整炉中位Si；均值混合仅用于训练降噪。",
        "- 标签可靠性权重只在训练阶段使用，不进入在线特征。",
        "- 真实铁水温度仍无合格标签，联合温度头继续阻止。",
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
        description="训练V11标签可靠性与Si目标平滑实验。"
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

