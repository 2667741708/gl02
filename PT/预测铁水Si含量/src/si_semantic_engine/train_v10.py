"""Evaluate explicit lag-band and spatial-field neurons for Si prediction.

All feature ranking and model selection are rebuilt inside April, May and the
fixed June validation folds.  The repeatedly used July segment is reported
only as a historical comparison.

Requirement:
    REQ-SI-LAG-FIELD-MODES-V10-20260727
"""

from __future__ import annotations

import argparse
import json
import platform
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
    _feature_recipes,
    _importance_features,
    _temperature_label_audit,
    _write_json,
    metrics,
)
from .train_v7 import _assemble_features
from .train_v8 import (
    LgbmSpec,
    _fit_predict,
    _fold_definitions,
    _quantile_distribution,
)
from .v10_features import (
    derive_lag_band_neurons,
    derive_spatial_field_modes,
)
from .v5_features import select_train_correlated_features


REQUIREMENT_ID = "REQ-SI-LAG-FIELD-MODES-V10-20260727"
RANDOM_STATE = 20260727


def _specs() -> tuple[LgbmSpec, ...]:
    return (
        LgbmSpec(
            "huber_leaf7_residual",
            "huber",
            7,
            35,
            "residual",
        ),
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
    )


def _assemble_v10_features(
    *,
    dataset_path: Path,
    heat_targets_path: Path,
    samples_path: Path,
    catalog_path: Path,
    temporal_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    combined, blocks = _assemble_features(
        dataset_path=dataset_path,
        heat_targets_path=heat_targets_path,
        samples_path=samples_path,
        catalog_path=catalog_path,
        temporal_dir=temporal_dir,
    )
    temporal = combined[blocks["temporal_columns"]]
    lag_bands = derive_lag_band_neurons(temporal)
    field_modes = derive_spatial_field_modes(temporal)
    overlap = set(combined.columns) & (
        set(lag_bands.columns) | set(field_modes.columns)
    )
    if overlap:
        raise RuntimeError(f"V10派生字段与既有字段重名：{sorted(overlap)[:5]}")
    combined = pd.concat(
        [combined, lag_bands, field_modes], axis=1
    ).replace([np.inf, -np.inf], np.nan)
    blocks = {
        **blocks,
        "lag_band_columns": list(lag_bands.columns),
        "field_mode_columns": list(field_modes.columns),
    }
    return combined, blocks


def _v10_recipes(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    blocks: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    old_recipes, old_audit = _feature_recipes(
        combined,
        train_mask,
        base_history=blocks["base_history"],
        temporal_columns=blocks["temporal_columns"],
        multiscale_columns=blocks["multiscale_columns"],
        heat_state_columns=blocks["heat_state_columns"],
        spatial_columns=blocks["spatial_columns"],
        chemistry_columns=blocks["chemistry_columns"],
    )
    train = combined.loc[train_mask]
    new_candidates = [
        *blocks["lag_band_columns"],
        *blocks["field_mode_columns"],
    ]
    new_ranked, new_ranking = select_train_correlated_features(
        train,
        train[TARGET],
        new_candidates,
        top_k=len(new_candidates),
    )
    new_importance250 = _importance_features(
        train, new_candidates, top_k=250
    )
    base_chemistry = old_recipes["base_plus_chemistry"]
    old_hybrid = old_recipes["base_chemistry_heat250"]

    def unique(*groups: Sequence[str]) -> list[str]:
        return list(
            dict.fromkeys(
                feature for group in groups for feature in group
            )
        )

    recipes = {
        "v9_reference": list(old_hybrid),
        "v10_new_corr100": unique(base_chemistry, new_ranked[:100]),
        "v10_new_corr250": unique(base_chemistry, new_ranked[:250]),
        "v10_hybrid_corr100": unique(old_hybrid, new_ranked[:100]),
        "v10_hybrid_corr250": unique(old_hybrid, new_ranked[:250]),
        "v10_hybrid_importance250": unique(
            old_hybrid, new_importance250
        ),
    }
    return recipes, {
        "selection_scope": "training_fold_only",
        "training_rows": int(train_mask.sum()),
        "old_feature_selection": old_audit,
        "new_candidate_count": len(new_candidates),
        "lag_band_feature_count": len(blocks["lag_band_columns"]),
        "field_mode_feature_count": len(blocks["field_mode_columns"]),
        "new_eligible_count": len(new_ranked),
        "new_ranking_top500": new_ranking.head(500).to_dict("records"),
        "new_importance250": new_importance250,
        "recipe_counts": {
            name: len(features) for name, features in recipes.items()
        },
    }


def _robust_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["robust_mae_score"],
        item["max_fold_mae"],
        -item["mean_hit_rate_abs_le_002"],
        item["candidate"],
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
    print(
        json.dumps(
            {
                "stage": "features_ready",
                "rows": len(combined),
                "lag_band_features": len(blocks["lag_band_columns"]),
                "field_mode_features": len(blocks["field_mode_columns"]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    fold_masks = _fold_definitions(combined)
    recipes_by_fold: dict[str, dict[str, list[str]]] = {}
    audit_by_fold: dict[str, Any] = {}
    for fold_name, (train_mask, _) in fold_masks.items():
        recipes_by_fold[fold_name], audit_by_fold[fold_name] = (
            _v10_recipes(combined, train_mask, blocks)
        )

    candidates: list[dict[str, Any]] = []
    recipe_names = tuple(next(iter(recipes_by_fold.values())).keys())
    for recipe_name in recipe_names:
        for spec in _specs():
            folds: dict[str, dict[str, float]] = {}
            for fold_name, (
                train_mask,
                evaluation_mask,
            ) in fold_masks.items():
                train = combined.loc[train_mask]
                evaluation = combined.loc[evaluation_mask]
                features = recipes_by_fold[fold_name][recipe_name]
                _, prediction, _ = _fit_predict(
                    spec, train, evaluation, features
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
            print(
                json.dumps(
                    {
                        "stage": "candidate_complete",
                        "candidate": candidates[-1]["candidate"],
                        "robust_mae_score": candidates[-1][
                            "robust_mae_score"
                        ],
                        "mean_hit_rate_abs_le_002": candidates[-1][
                            "mean_hit_rate_abs_le_002"
                        ],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    ranking = sorted(candidates, key=_robust_key)
    best_robust_score = ranking[0]["robust_mae_score"]
    pareto_pool = [
        item
        for item in ranking
        if item["robust_mae_score"] <= best_robust_score + 0.00015
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
    final_recipes, final_audit = _v10_recipes(
        combined, train_mask, blocks
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
            "status": "experimental_offline_v10",
        },
        models_dir / "selected_v10.joblib",
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
    _write_json(output_dir / "feature_importance.json", importance[:500])
    temperature_audit = _temperature_label_audit(
        combined, blocks["heat_targets"]
    )
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v10",
        "selection_contract": (
            "lag/field features and all rankings rebuilt inside April/May "
            "expanding folds and fixed June validation; candidates within "
            "0.00015 robust-MAE form a Pareto pool; July is historical "
            "comparison only"
        ),
        "pareto_policy": {
            "robust_mae_tolerance": 0.00015,
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
            "si_distribution_head": "trained_experimental_offline_v10",
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
            "selected_features": selected_features,
            "windows_minutes": blocks["windows_minutes"],
            "lag_bands_minutes": [
                [0, 30],
                [30, 60],
                [60, 120],
                [120, 240],
                [240, 480],
            ],
            "lag_band_feature_count": len(blocks["lag_band_columns"]),
            "field_mode_feature_count": len(
                blocks["field_mode_columns"]
            ),
            "spatial_modes": {
                "static_pressure": "A-F harmonic 1/2 by three heights",
                "body_temperature": (
                    "A-H harmonic 1/2 by layers 7-16 plus vertical coherence"
                ),
                "top_fields": "A-D harmonic 1/2",
            },
            "all_features_strictly_before_cutoff": True,
            "all_feature_selection_training_fold_only": True,
            "taphole_temperature_is_proxy_only": True,
            "cooling_wall_heat_loss_status": (
                "not_in_current_133_point_catalog"
            ),
        },
    )
    report = [
        "# V10 非重叠时延带与空间场模态实验",
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
        (
            f"- 新增时延带/空间场特征："
            f"{len(blocks['lag_band_columns'])} / "
            f"{len(blocks['field_mode_columns'])}"
        ),
        "",
        "- 真实铁水温度仍为0个合格标签，联合温度头继续阻止。",
        "- 七月为多次读取的历史对照，不是新的盲测。",
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
        description="训练V10非重叠时延带和空间场模态Si模型。"
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
