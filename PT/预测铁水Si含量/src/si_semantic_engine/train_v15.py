"""Fold-internal best response-lag experiment for representative Si.

The selector ranks non-overlapping lag-band neurons against the residual from
the already-published Si history baseline.  One lag is retained per physical
variable and response family inside every training fold.

Requirement:
    REQ-SI-BEST-RESPONSE-LAG-V15-20260727
"""

from __future__ import annotations

import argparse
import json
import platform
import re
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
from .train_v10 import _robust_key, _specs
from .train_v13 import _assemble_v13_features, _v13_recipes


REQUIREMENT_ID = "REQ-SI-BEST-RESPONSE-LAG-V15-20260727"
RANDOM_STATE = 20260727

_BAND_PATTERN = re.compile(
    r"^(?P<source>lagband|lagmoment)__(?P<variable>.+?)"
    r"__m(?P<start>\d+)_(?P<end>\d+)__"
    r"(?P<statistic>mean|std|rms|cv_abs)$"
)
_SHOCK_PATTERN = re.compile(
    r"^lagshock__(?P<variable>.+?)__recent_vs_m"
    r"(?P<start>\d+)_(?P<end>\d+)__"
    r"(?P<statistic>pooled_z|std_ratio)$"
)
_DIFFERENCE_PATTERN = re.compile(
    r"^lagprofile__(?P<variable>.+?)__recent_minus_m"
    r"(?P<start>\d+)_(?P<end>\d+)__mean$"
)


def _unique(*groups: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group))


def response_lag_descriptor(column: str) -> dict[str, Any] | None:
    """Parse a response-lag feature into physical variable and family."""

    match = _BAND_PATTERN.match(str(column))
    if match:
        statistic = match.group("statistic")
        family = {
            "mean": "band_mean",
            "std": "band_volatility",
            "rms": "band_energy",
            "cv_abs": "band_relative_volatility",
        }[statistic]
    else:
        match = _SHOCK_PATTERN.match(str(column))
        if match:
            statistic = match.group("statistic")
            family = {
                "pooled_z": "standardized_mean_shock",
                "std_ratio": "volatility_ratio",
            }[statistic]
        else:
            match = _DIFFERENCE_PATTERN.match(str(column))
            if not match:
                return None
            statistic = "recent_minus_older_mean"
            family = "mean_difference"
    start = int(match.group("start"))
    end = int(match.group("end"))
    return {
        "feature": str(column),
        "variable": match.group("variable"),
        "family": family,
        "statistic": statistic,
        "lag_start_minutes": start,
        "lag_end_minutes": end,
        "response_center_minutes": (start + end) / 2.0,
    }


def select_best_response_lags(
    train: pd.DataFrame,
    target_residual: pd.Series,
    candidates: Sequence[str],
    *,
    minimum_coverage: float = 0.50,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Select one strongest train-only lag per variable and family."""

    target = pd.to_numeric(target_residual, errors="coerce")
    records: list[dict[str, Any]] = []
    for column in candidates:
        descriptor = response_lag_descriptor(str(column))
        if descriptor is None or column not in train:
            continue
        values = pd.to_numeric(train[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        coverage = float(values.notna().mean())
        if coverage < minimum_coverage or values.nunique(dropna=True) <= 1:
            continue
        correlation = float(values.corr(target, method="spearman"))
        if not np.isfinite(correlation):
            continue
        records.append(
            {
                **descriptor,
                "spearman_to_history_residual": correlation,
                "abs_spearman_to_history_residual": abs(correlation),
                "train_non_null_ratio": coverage,
            }
        )
    ordered = sorted(
        records,
        key=lambda item: (
            item["variable"],
            item["family"],
            -item["abs_spearman_to_history_residual"],
            item["response_center_minutes"],
            item["feature"],
        ),
    )
    selected_records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in ordered:
        key = (item["variable"], item["family"])
        if key in seen:
            continue
        seen.add(key)
        selected_records.append(item)
    ranked = sorted(
        selected_records,
        key=lambda item: (
            -item["abs_spearman_to_history_residual"],
            item["variable"],
            item["family"],
        ),
    )
    return [str(item["feature"]) for item in ranked], ranked


def _v15_recipes(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    blocks: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    train = combined.loc[train_mask]
    fallback = float(train[TARGET].median())
    residual = train[TARGET] - _history_baseline(
        train, fallback=fallback
    )
    lag_candidates = [
        *blocks["lag_band_columns"],
        *blocks["lag_moment_columns"],
    ]
    best_lags, lag_audit = select_best_response_lags(
        train, residual, lag_candidates
    )
    v13_recipes, v13_audit = _v13_recipes(
        combined, train_mask, blocks
    )
    base = _unique(
        blocks["base_history"], blocks["chemistry_columns"]
    )
    v13_reference = v13_recipes["v13_allnew_importance350"]
    recipes = {
        "v13_reference": v13_reference,
        "best_lag_top350": _unique(base, best_lags[:350]),
        "best_lag_all": _unique(base, best_lags),
        "v13_plus_best_lag200": _unique(
            v13_reference, best_lags[:200]
        ),
    }
    return recipes, {
        "selection_scope": "training_fold_only",
        "selection_target": (
            "Si_representative minus published-history baseline"
        ),
        "minimum_coverage": 0.50,
        "candidate_count": len(lag_candidates),
        "selected_variable_family_count": len(best_lags),
        "selected_response_lags": lag_audit,
        "v13_selection": v13_audit,
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
    fold_masks = _fold_definitions(combined)
    recipes_by_fold: dict[str, dict[str, list[str]]] = {}
    audit_by_fold: dict[str, Any] = {}
    for fold_name, (train_mask, _) in fold_masks.items():
        recipes_by_fold[fold_name], audit_by_fold[fold_name] = (
            _v15_recipes(combined, train_mask, blocks)
        )
    print(
        json.dumps(
            {
                "stage": "features_ready",
                "rows": len(combined),
                "fold_selected_counts": {
                    name: audit["selected_variable_family_count"]
                    for name, audit in audit_by_fold.items()
                },
            },
            ensure_ascii=False,
        ),
        flush=True,
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
    final_recipes, final_audit = _v15_recipes(
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
            "status": "experimental_offline_v15",
            "selection": final_audit["selected_response_lags"],
        },
        models_dir / "selected_v15.joblib",
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
        "model_status": "experimental_offline_v15",
        "selection_contract": (
            "one response lag per physical variable and family is selected "
            "against the published-history Si residual inside each fold; "
            "July is historical comparison only"
        ),
        "pareto_policy": {
            "robust_mae_tolerance": 0.00015,
            "pool_size": len(pareto_pool),
            "secondary_objective": "mean_hit_rate_abs_le_002",
        },
        "selected": {
            **selected,
            "feature_count": len(selected_features),
            "selected_response_lag_count": final_audit[
                "selected_variable_family_count"
            ],
            "historical_test": test_metrics,
            "distribution_test": distribution_metrics,
        },
        "candidate_ranking": ranking,
        "joint_task_readiness": {
            "si_distribution_head": "trained_experimental_offline_v15",
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
            "response_families": [
                "band_mean",
                "band_volatility",
                "band_energy",
                "band_relative_volatility",
                "standardized_mean_shock",
                "volatility_ratio",
                "mean_difference",
            ],
            "selection_target": (
                "Si_representative minus published-history baseline"
            ),
            "one_lag_per_variable_and_family": True,
            "all_features_strictly_before_cutoff": True,
            "all_feature_selection_training_fold_only": True,
            "taphole_temperature_is_proxy_only": True,
        },
    )
    report = [
        "# V15 训练折内最佳响应时延报告",
        "",
        (
            f"- 最终训练折选出变量×响应族："
            f"{final_audit['selected_variable_family_count']}"
        ),
        f"- 选中候选：`{selected['candidate']}`",
        f"- 预测试稳健分数：{selected['robust_mae_score']:.6f}",
        (
            f"- 历史7月 MAE / ±0.02 / ±0.05："
            f"{test_metrics['mae']:.6f} / "
            f"{test_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        "",
        "- 时延选择目标为相对已发布历史Si基线的残差。",
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
        description="训练V15训练折内最佳响应时延紧凑模型。"
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
