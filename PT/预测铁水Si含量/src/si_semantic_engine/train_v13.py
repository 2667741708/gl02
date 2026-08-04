"""Evaluate disjoint lag-band volatility and shock neurons.

All feature ranking and candidate selection are rebuilt inside the April,
May and fixed June folds.  July remains a read-once historical comparison.

Requirement:
    REQ-SI-LAG-MOMENT-NEURONS-V13-20260727
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
    _importance_features,
    _temperature_label_audit,
    _write_json,
    metrics,
)
from .train_v8 import (
    LgbmSpec,
    _fit_predict,
    _fold_definitions,
    _quantile_distribution,
)
from .train_v10 import (
    _assemble_v10_features,
    _robust_key,
    _specs,
    _v10_recipes,
)
from .v13_features import derive_lag_moment_neurons
from .v5_features import select_train_correlated_features


REQUIREMENT_ID = "REQ-SI-LAG-MOMENT-NEURONS-V13-20260727"
RANDOM_STATE = 20260727


def _unique(*groups: Sequence[str]) -> list[str]:
    return list(
        dict.fromkeys(feature for group in groups for feature in group)
    )


def _assemble_v13_features(
    *,
    dataset_path: Path,
    heat_targets_path: Path,
    samples_path: Path,
    catalog_path: Path,
    temporal_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    combined, blocks = _assemble_v10_features(
        dataset_path=dataset_path,
        heat_targets_path=heat_targets_path,
        samples_path=samples_path,
        catalog_path=catalog_path,
        temporal_dir=temporal_dir,
    )
    moments = derive_lag_moment_neurons(
        combined[blocks["temporal_columns"]]
    )
    overlap = set(combined.columns) & set(moments.columns)
    if overlap:
        raise RuntimeError(
            f"V13派生字段与既有字段重名：{sorted(overlap)[:5]}"
        )
    combined = pd.concat([combined, moments], axis=1).replace(
        [np.inf, -np.inf], np.nan
    )
    return combined, {
        **blocks,
        "lag_moment_columns": list(moments.columns),
    }


def _v13_recipes(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    blocks: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    v10_recipes, v10_audit = _v10_recipes(
        combined, train_mask, blocks
    )
    train = combined.loc[train_mask]
    moment_candidates = blocks["lag_moment_columns"]
    moment_ranked, moment_ranking = select_train_correlated_features(
        train,
        train[TARGET],
        moment_candidates,
        top_k=len(moment_candidates),
    )
    moment_importance250 = _importance_features(
        train, moment_candidates, top_k=250
    )
    all_new_candidates = [
        *blocks["lag_band_columns"],
        *blocks["field_mode_columns"],
        *moment_candidates,
    ]
    all_new_importance350 = _importance_features(
        train, all_new_candidates, top_k=350
    )
    old_hybrid = v10_recipes["v9_reference"]
    recipes = {
        "v10_reference": v10_recipes[
            "v10_hybrid_importance250"
        ],
        "v13_moment_corr100": _unique(
            old_hybrid, moment_ranked[:100]
        ),
        "v13_moment_corr250": _unique(
            old_hybrid, moment_ranked[:250]
        ),
        "v13_moment_importance250": _unique(
            old_hybrid, moment_importance250
        ),
        "v13_allnew_importance350": _unique(
            old_hybrid, all_new_importance350
        ),
    }
    return recipes, {
        "selection_scope": "training_fold_only",
        "training_rows": int(train_mask.sum()),
        "v10_selection": v10_audit,
        "lag_moment_candidate_count": len(moment_candidates),
        "moment_ranking_top500": moment_ranking.head(500).to_dict(
            "records"
        ),
        "moment_importance250": moment_importance250,
        "all_new_importance350": all_new_importance350,
        "recipe_counts": {
            name: len(features) for name, features in recipes.items()
        },
    }


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
    combined, blocks = _assemble_v13_features(
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
                "lag_moment_features": len(
                    blocks["lag_moment_columns"]
                ),
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
            _v13_recipes(combined, train_mask, blocks)
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
                features = recipes_by_fold[fold_name][recipe_name]
                _, prediction, _ = _fit_predict(
                    spec,
                    combined.loc[train_mask],
                    combined.loc[evaluation_mask],
                    features,
                )
                folds[fold_name] = metrics(
                    combined.loc[
                        evaluation_mask, TARGET
                    ].to_numpy(float),
                    prediction,
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
    ranking = sorted(candidates, key=_robust_key)
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
            item["max_fold_mae"],
            item["candidate"],
        ),
    )
    selected_spec = LgbmSpec(**selected["spec"])
    train_mask = combined["experiment_split"].eq("train")
    test_mask = combined["experiment_split"].eq("test")
    final_recipes, final_audit = _v13_recipes(
        combined, train_mask, blocks
    )
    selected_features = final_recipes[selected["recipe"]]
    model, prediction, fallback = _fit_predict(
        selected_spec,
        combined.loc[train_mask],
        combined.loc[test_mask],
        selected_features,
    )
    test = combined.loc[test_mask].copy()
    test_metrics = metrics(test[TARGET].to_numpy(float), prediction)
    distribution, distribution_models = _quantile_distribution(
        selected_spec,
        combined.loc[train_mask],
        test,
        selected_features,
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
            "status": "experimental_offline_v13",
        },
        models_dir / "selected_v13.joblib",
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
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v13",
        "selection_contract": (
            "disjoint-band moment features and rankings rebuilt inside "
            "April/May expanding folds and fixed June validation; July "
            "is historical comparison only"
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
            "si_distribution_head": "trained_experimental_offline_v13",
            **_temperature_label_audit(
                combined, blocks["heat_targets"]
            ),
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
            "lag_moment_feature_count": len(
                blocks["lag_moment_columns"]
            ),
            "recovered_statistics": [
                "non_overlapping_band_std",
                "non_overlapping_band_rms",
                "absolute_cv",
                "standardized_mean_shock",
                "volatility_ratio",
                "volatility_profile_slope",
            ],
            "moment_reconstruction": (
                "subtract cumulative count/sum/sum-of-squares; source "
                "std is interpreted as sample standard deviation"
            ),
            "all_features_strictly_before_cutoff": True,
            "all_feature_selection_training_fold_only": True,
            "taphole_temperature_is_proxy_only": True,
        },
    )
    report = [
        "# V13 非重叠时延波动与冲击神经元报告",
        "",
        f"- 新增时延矩特征：{len(blocks['lag_moment_columns'])}",
        f"- 选中候选：`{selected['candidate']}`",
        f"- 预测试稳健分数：{selected['robust_mae_score']:.6f}",
        (
            f"- 历史7月 MAE / ±0.02 / ±0.05："
            f"{test_metrics['mae']:.6f} / "
            f"{test_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        "",
        "- 真实铁水温度标签仍缺失，温度联合头未训练。",
        "- 未达到0.02目标前保持离线实验状态。",
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
    return result["selected"]


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="训练V13非重叠时延波动与冲击神经元模型。"
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
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
