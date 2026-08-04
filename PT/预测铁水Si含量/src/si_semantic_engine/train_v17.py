"""CatBoost ordered-boosting experiment on the frozen V13 feature recipes.

The expensive V13 fold-internal selection is reconstructed from its immutable
selection audit after every input hash, training-row count and feature count
has been verified.  No validation or historical-test target is reused.

Requirement:
    REQ-SI-CATBOOST-ORDERED-V17-20260727
"""

from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import catboost
import joblib
import numpy as np
import pandas as pd
import sklearn
from catboost import CatBoostRegressor

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
from .train_v8 import _fold_definitions
from .train_v10 import _robust_key
from .train_v13 import _assemble_v13_features


REQUIREMENT_ID = "REQ-SI-CATBOOST-ORDERED-V17-20260727"
RANDOM_STATE = 20260727


@dataclass(frozen=True)
class CatSpec:
    name: str
    loss_function: str
    depth: int
    target_mode: str
    boosting_type: str = "Ordered"
    iterations: int = 300
    learning_rate: float = 0.03
    l2_leaf_reg: float = 10.0
    random_strength: float = 1.0
    recency_half_life_days: float | None = None


def _specs() -> tuple[CatSpec, ...]:
    return (
        CatSpec("ordered_mae_d6_residual", "MAE", 6, "residual"),
        CatSpec("ordered_rmse_d6_residual", "RMSE", 6, "residual"),
        CatSpec("ordered_mae_d6_direct", "MAE", 6, "direct"),
    )


def _unique(*groups: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group))


def _verify_cache_inputs(
    manifest: dict[str, Any],
    *,
    dataset_path: Path,
    heat_targets_path: Path,
    samples_path: Path,
    catalog_path: Path,
    temporal_dir: Path,
) -> None:
    expected = manifest["inputs"]
    actual = {
        "dataset": sha256_file(dataset_path),
        "heat_targets": sha256_file(heat_targets_path),
        "samples": sha256_file(samples_path),
        "sensor_catalog": sha256_file(catalog_path),
        "temporal_manifest": sha256_file(
            temporal_dir / "manifest.json"
        ),
    }
    mismatches = {
        key: {"expected": expected.get(key), "actual": value}
        for key, value in actual.items()
        if expected.get(key) != value
    }
    if mismatches:
        raise RuntimeError(
            "V13选择缓存输入哈希不一致："
            + json.dumps(mismatches, ensure_ascii=False)
        )


def reconstruct_v13_recipes(
    blocks: dict[str, Any],
    audit_entry: dict[str, Any],
    *,
    expected_training_rows: int,
    available_columns: Sequence[str],
) -> dict[str, list[str]]:
    """Reconstruct V9/V13 recipes from an immutable selection audit."""

    if int(audit_entry["training_rows"]) != expected_training_rows:
        raise RuntimeError("V13选择缓存训练行数不一致")
    old = audit_entry["v10_selection"]["old_feature_selection"]
    derived = [
        str(item["feature"])
        for item in old["derived_ranking_top300"][:250]
    ]
    v9_reference = _unique(
        blocks["base_history"],
        blocks["chemistry_columns"],
        derived,
    )
    all_new = [
        str(feature)
        for feature in audit_entry["all_new_importance350"]
    ]
    v13_reference = _unique(v9_reference, all_new)
    recipes = {
        "v9_reference": v9_reference,
        "v13_reference": v13_reference,
    }
    expected_counts = {
        "v9_reference": int(
            audit_entry["v10_selection"]["recipe_counts"][
                "v9_reference"
            ]
        ),
        "v13_reference": int(
            audit_entry["recipe_counts"][
                "v13_allnew_importance350"
            ]
        ),
    }
    available = set(available_columns)
    for name, features in recipes.items():
        if len(features) != expected_counts[name]:
            raise RuntimeError(
                f"{name}缓存配方数量不一致："
                f"{len(features)} != {expected_counts[name]}"
            )
        missing = sorted(set(features) - available)
        if missing:
            raise RuntimeError(
                f"{name}缓存特征在当前输入中缺失：{missing[:5]}"
            )
    return recipes


def _model(spec: CatSpec, *, loss_function: str | None = None) -> CatBoostRegressor:
    return CatBoostRegressor(
        loss_function=loss_function or spec.loss_function,
        iterations=spec.iterations,
        learning_rate=spec.learning_rate,
        depth=spec.depth,
        l2_leaf_reg=spec.l2_leaf_reg,
        random_strength=spec.random_strength,
        boosting_type=spec.boosting_type,
        bootstrap_type="Bayesian",
        bagging_temperature=1.0,
        random_seed=RANDOM_STATE,
        thread_count=-1,
        verbose=False,
        allow_writing_files=False,
    )


def _fit_predict(
    spec: CatSpec,
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    features: Sequence[str],
) -> tuple[CatBoostRegressor, np.ndarray, float]:
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
    )
    prediction = model.predict(evaluation[list(features)])
    if spec.target_mode == "residual":
        prediction = prediction + evaluation_baseline.to_numpy(float)
    return model, np.asarray(prediction, dtype=float), fallback


def _quantile_distribution(
    spec: CatSpec,
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: Sequence[str],
) -> tuple[tuple[np.ndarray, np.ndarray, np.ndarray], dict[str, Any]]:
    fallback = float(train[TARGET].median())
    train_baseline = _history_baseline(train, fallback=fallback)
    test_baseline = _history_baseline(test, fallback=fallback)
    target = train[TARGET].to_numpy(float)
    if spec.target_mode == "residual":
        target = target - train_baseline.to_numpy(float)
    predictions: list[np.ndarray] = []
    models: dict[str, Any] = {}
    for quantile in (0.10, 0.50, 0.90):
        model = _model(
            spec, loss_function=f"Quantile:alpha={quantile}"
        )
        weights = _recency_weights(
            train["prediction_cutoff_ts"],
            spec.recency_half_life_days,
        )
        model.fit(
            train[list(features)],
            target,
            sample_weight=weights,
        )
        prediction = np.asarray(
            model.predict(test[list(features)]), dtype=float
        )
        if spec.target_mode == "residual":
            prediction = (
                prediction + test_baseline.to_numpy(float)
            )
        predictions.append(prediction)
        models[f"q{int(quantile * 100):02d}"] = model
    stacked = np.sort(np.vstack(predictions), axis=0)
    return (stacked[0], stacked[1], stacked[2]), models


def run_experiment(
    *,
    dataset_path: Path,
    heat_targets_path: Path,
    samples_path: Path,
    catalog_path: Path,
    temporal_dir: Path,
    v13_selection_audit_path: Path,
    v13_run_manifest_path: Path,
    output_dir: Path,
    specs: Sequence[CatSpec] | None = None,
    requirement_id: str = REQUIREMENT_ID,
    model_version: str = "v17",
    report_title: str = "V17 CatBoost有序提升报告",
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    models_dir = output_dir / "models"
    models_dir.mkdir(exist_ok=True)
    manifest = json.loads(
        v13_run_manifest_path.read_text(encoding="utf-8")
    )
    selection_audit = json.loads(
        v13_selection_audit_path.read_text(encoding="utf-8")
    )
    _verify_cache_inputs(
        manifest,
        dataset_path=dataset_path,
        heat_targets_path=heat_targets_path,
        samples_path=samples_path,
        catalog_path=catalog_path,
        temporal_dir=temporal_dir,
    )
    combined, blocks = _assemble_v13_features(
        dataset_path=dataset_path,
        heat_targets_path=heat_targets_path,
        samples_path=samples_path,
        catalog_path=catalog_path,
        temporal_dir=temporal_dir,
    )
    fold_masks = _fold_definitions(combined)
    recipes_by_fold: dict[str, dict[str, list[str]]] = {}
    for fold_name, (train_mask, _) in fold_masks.items():
        recipes_by_fold[fold_name] = reconstruct_v13_recipes(
            blocks,
            selection_audit["folds"][fold_name],
            expected_training_rows=int(train_mask.sum()),
            available_columns=combined.columns,
        )
    print(
        json.dumps(
            {
                "stage": "cache_verified",
                "rows": len(combined),
                "v13_manifest_requirement": manifest[
                    "requirement_id"
                ],
                "fold_recipe_counts": {
                    name: {
                        recipe: len(features)
                        for recipe, features in recipes.items()
                    }
                    for name, recipes in recipes_by_fold.items()
                },
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    active_specs = tuple(specs) if specs is not None else _specs()
    candidates: list[dict[str, Any]] = []
    # V13 already dominates V9 in the fixed pretest policy.  The failed
    # 001 runtime showed that crossing both recipes with five ordered
    # boosters is not a viable experimental inner loop.
    for recipe_name in ("v13_reference",):
        for spec in active_specs:
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
                    combined.loc[evaluation_mask, TARGET].to_numpy(
                        float
                    ),
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
                "spec": asdict(spec),
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
    selected_spec = CatSpec(**selected["spec"])
    train_mask = combined["experiment_split"].eq("train")
    test_mask = combined["experiment_split"].eq("test")
    final_recipes = reconstruct_v13_recipes(
        blocks,
        selection_audit["final_train"],
        expected_training_rows=int(train_mask.sum()),
        available_columns=combined.columns,
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
            "status": f"experimental_offline_{model_version}",
        },
        models_dir / f"selected_{model_version}.joblib",
    )
    importance = sorted(
        [
            {"feature": feature, "importance": float(value)}
            for feature, value in zip(
                selected_features,
                model.get_feature_importance(),
            )
        ],
        key=lambda item: item["importance"],
        reverse=True,
    )
    _write_json(output_dir / "feature_importance.json", importance[:500])
    result = {
        "requirement_id": requirement_id,
        "model_status": f"experimental_offline_{model_version}",
        "selection_contract": (
            "V13 fold recipes reconstructed only after immutable input "
            "hash, training-row and feature-count verification; CatBoost "
            "candidate selection uses April/May/fixed-June only"
        ),
        "cache_contract": {
            "source_selection_audit": str(
                v13_selection_audit_path.resolve()
            ),
            "source_run_manifest": str(
                v13_run_manifest_path.resolve()
            ),
            "input_hashes_verified": True,
            "validation_or_test_targets_cached": False,
        },
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
            "si_distribution_head": (
                f"trained_experimental_offline_{model_version}"
            ),
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
        output_dir / "feature_contract.json",
        {
            "selected_features": selected_features,
            "source_recipe": selected["recipe"],
            "source_v13_cache_verified": True,
            "all_features_strictly_before_cutoff": True,
            "taphole_temperature_is_proxy_only": True,
        },
    )
    report = [
        f"# {report_title}",
        "",
        f"- 选中候选：`{selected['candidate']}`",
        f"- 预测试稳健分数：{selected['robust_mae_score']:.6f}",
        (
            f"- 历史7月 MAE / ±0.02 / ±0.05："
            f"{test_metrics['mae']:.6f} / "
            f"{test_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        "",
        "- V13折内特征缓存已通过输入哈希、行数和数量校验。",
        "- 真实铁水温度标签仍缺失，温度联合头未训练。",
        "- 未达到0.02目标前保持离线实验状态。",
        "",
    ]
    (output_dir / "report.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    run_manifest = {
        "requirement_id": requirement_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "runtime": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "catboost": catboost.__version__,
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
            "v13_selection_audit": sha256_file(
                v13_selection_audit_path
            ),
            "v13_run_manifest": sha256_file(
                v13_run_manifest_path
            ),
        },
        "artifacts": _artifact_hashes(output_dir),
    }
    _write_json(output_dir / "run_manifest.json", run_manifest)
    return result["selected"]


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="训练V17 CatBoost有序提升模型。"
    )
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--heat-targets", type=Path, required=True)
    cli.add_argument("--samples", type=Path, required=True)
    cli.add_argument("--sensor-catalog", type=Path, required=True)
    cli.add_argument("--temporal-dir", type=Path, required=True)
    cli.add_argument(
        "--v13-selection-audit", type=Path, required=True
    )
    cli.add_argument("--v13-run-manifest", type=Path, required=True)
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
        v13_selection_audit_path=args.v13_selection_audit,
        v13_run_manifest_path=args.v13_run_manifest,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
