"""Fold-internal semantic-group latent thermal-state experiment.

Each process group is compressed into supervised PLS residual factors using
training rows only.  Downstream models see prior published chemistry/history
plus the low-dimensional factors, not thousands of unstructured variables.

Requirement:
    REQ-SI-SEMANTIC-LATENT-STATE-V14-20260727
"""

from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import joblib
import lightgbm
import numpy as np
import pandas as pd
import sklearn
import xgboost
from lightgbm import LGBMRegressor
from sklearn.cross_decomposition import PLSRegression
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from .formal_dataset import sha256_file
from .train_v3 import TARGET
from .train_v6 import (
    _artifact_hashes,
    _history_baseline,
    _temperature_label_audit,
    _write_json,
    metrics,
)
from .train_v8 import _fold_definitions
from .train_v13 import _assemble_v13_features
from .v5_features import select_train_correlated_features


REQUIREMENT_ID = "REQ-SI-SEMANTIC-LATENT-STATE-V14-20260727"
RANDOM_STATE = 20260727
MAX_COMPONENTS = 3
TOP_K_PER_GROUP = 80

GROUP_VARIABLES = {
    "thermal_input": (
        "T_blast",
        "TFT",
        "Q_blast",
        "P_blast",
        "Q_O2",
        "O2_rate",
        "PCI_set",
        "PCI_rate",
    ),
    "gas_utilization": (
        "GasUtil",
        "T_top_A",
        "T_top_B",
        "T_top_C",
        "T_top_D",
        "P_top",
        "P_top_gas_A",
        "P_top_gas_B",
        "P_top_gas_C",
        "P_top_gas_D",
    ),
    "permeability": ("PI", "DP_upper", "DP_lower", "DP_total"),
    "burden_motion": ("L", "L_south", "L_north"),
    "taphole_proxy": ("T_taphole_1", "T_taphole_2"),
}


def _variable_group(variable: str) -> str | None:
    for group, variables in GROUP_VARIABLES.items():
        if variable in variables:
            return group
    if variable.startswith("P_static_"):
        return "static_pressure_field"
    if variable.startswith("T_body_"):
        return "body_thermal_field"
    return None


def _semantic_feature_group(column: str) -> str | None:
    if "fieldmode__static_" in column:
        return "static_pressure_field"
    if "fieldmode__body_" in column:
        return "body_thermal_field"
    if "fieldmode__top_" in column:
        return "gas_utilization"
    for group, variables in GROUP_VARIABLES.items():
        for variable in variables:
            if (
                f"__{variable}__" in column
                or f"__{variable}_" in column
            ):
                return group
    if "__P_static_" in column:
        return "static_pressure_field"
    if "__T_body_" in column:
        return "body_thermal_field"
    return None


def _group_feature_candidates(
    combined: pd.DataFrame,
    blocks: dict[str, Any],
    catalog_path: Path,
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        name: [] for name in (*GROUP_VARIABLES, "static_pressure_field", "body_thermal_field")
    }
    dynamic_columns = [
        *blocks["temporal_columns"],
        *blocks["multiscale_columns"],
        *blocks["heat_state_columns"],
        *blocks["spatial_columns"],
        *blocks["lag_band_columns"],
        *blocks["field_mode_columns"],
        *blocks["lag_moment_columns"],
    ]
    for column in dynamic_columns:
        group = _semantic_feature_group(column)
        if group is not None:
            groups[group].append(column)

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for point in catalog["points"]:
        variable = str(point["canonical_id"])
        group = _variable_group(variable)
        if group is None:
            continue
        short_name = str(point["database"]["short_name"])
        prefix = f"sensor__{short_name}__"
        groups[group].extend(
            column
            for column in combined.columns
            if str(column).startswith(prefix)
        )
    output = {
        group: list(dict.fromkeys(columns))
        for group, columns in groups.items()
        if columns
    }
    if any(
        column.startswith("target__")
        for columns in output.values()
        for column in columns
    ):
        raise RuntimeError("V14工艺组候选意外包含target字段")
    return output


def _base_visible_features(combined: pd.DataFrame) -> list[str]:
    prefixes = ("history__", "history_v4__", "chem_history__")
    return [
        column
        for column in combined.columns
        if str(column).startswith(prefixes)
        and pd.api.types.is_numeric_dtype(combined[column])
    ]


def _fit_latent_factors(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    residual_target: np.ndarray,
    group_candidates: dict[str, list[str]],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    train_factors: dict[str, np.ndarray] = {}
    evaluation_factors: dict[str, np.ndarray] = {}
    transformers: dict[str, Any] = {}
    audit: dict[str, Any] = {}
    target_series = pd.Series(
        residual_target, index=train.index, dtype=float
    )
    for group, candidates in group_candidates.items():
        selected, ranking = select_train_correlated_features(
            train,
            target_series,
            candidates,
            top_k=min(TOP_K_PER_GROUP, len(candidates)),
        )
        if not selected:
            continue
        imputer = SimpleImputer(strategy="median")
        scaler = StandardScaler()
        train_imputed = imputer.fit_transform(train[selected])
        train_scaled = scaler.fit_transform(train_imputed)
        evaluation_scaled = scaler.transform(
            imputer.transform(evaluation[selected])
        )
        component_count = min(
            MAX_COMPONENTS,
            train_scaled.shape[1],
            max(1, train_scaled.shape[0] - 1),
        )
        pls = PLSRegression(
            n_components=component_count,
            scale=False,
            max_iter=1000,
        )
        pls.fit(train_scaled, residual_target)
        train_scores = pls.transform(train_scaled)
        evaluation_scores = pls.transform(evaluation_scaled)
        for component in range(component_count):
            name = f"latent__{group}__c{component + 1}"
            train_factors[name] = train_scores[:, component]
            evaluation_factors[name] = evaluation_scores[:, component]
        loadings = []
        for component in range(component_count):
            order = np.argsort(
                np.abs(pls.x_loadings_[:, component])
            )[::-1][:10]
            loadings.append(
                [
                    {
                        "feature": selected[index],
                        "loading": float(
                            pls.x_loadings_[index, component]
                        ),
                    }
                    for index in order
                ]
            )
        transformers[group] = {
            "features": selected,
            "imputer": imputer,
            "scaler": scaler,
            "pls": pls,
        }
        audit[group] = {
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "components": component_count,
            "ranking_top20": ranking.head(20).to_dict("records"),
            "component_top_loadings": loadings,
        }
    if not train_factors:
        raise RuntimeError("V14未生成任何潜在热状态因子")
    return (
        pd.DataFrame(train_factors, index=train.index),
        pd.DataFrame(evaluation_factors, index=evaluation.index),
        transformers,
        audit,
    )


def _candidate_factories() -> dict[str, Callable[[], Pipeline]]:
    return {
        "ridge_alpha10": lambda: Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", Ridge(alpha=10.0)),
            ]
        ),
        "extra_leaf10": lambda: Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    ExtraTreesRegressor(
                        n_estimators=500,
                        min_samples_leaf=10,
                        max_features=0.8,
                        random_state=RANDOM_STATE,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
        "xgb_depth2": lambda: Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    XGBRegressor(
                        n_estimators=400,
                        learning_rate=0.025,
                        max_depth=2,
                        min_child_weight=20,
                        subsample=0.85,
                        colsample_bytree=0.8,
                        reg_alpha=0.1,
                        reg_lambda=8.0,
                        objective="reg:pseudohubererror",
                        random_state=RANDOM_STATE,
                        n_jobs=-1,
                        verbosity=0,
                    ),
                ),
            ]
        ),
        "lgbm_leaf7": lambda: Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    LGBMRegressor(
                        objective="huber",
                        n_estimators=500,
                        learning_rate=0.025,
                        num_leaves=7,
                        min_child_samples=35,
                        subsample=0.85,
                        subsample_freq=1,
                        colsample_bytree=0.8,
                        reg_alpha=0.1,
                        reg_lambda=8.0,
                        random_state=RANDOM_STATE,
                        n_jobs=-1,
                        verbosity=-1,
                    ),
                ),
            ]
        ),
    }


def _design_matrix(
    frame: pd.DataFrame,
    factors: pd.DataFrame,
    base_features: Sequence[str],
    components: int,
) -> tuple[pd.DataFrame, list[str]]:
    factor_columns = [
        column
        for column in factors.columns
        if int(column.rsplit("c", 1)[-1]) <= components
    ]
    columns = [*base_features, *factor_columns]
    matrix = pd.concat(
        [frame[list(base_features)], factors[factor_columns]], axis=1
    )
    return matrix, columns


def _fit_quantile_models(
    train_matrix: pd.DataFrame,
    test_matrix: pd.DataFrame,
    residual_target: np.ndarray,
    baseline: np.ndarray,
) -> tuple[np.ndarray, dict[str, Pipeline]]:
    predictions: list[np.ndarray] = []
    models: dict[str, Pipeline] = {}
    for quantile in (0.10, 0.50, 0.90):
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    LGBMRegressor(
                        objective="quantile",
                        alpha=quantile,
                        n_estimators=500,
                        learning_rate=0.025,
                        num_leaves=7,
                        min_child_samples=35,
                        reg_lambda=8.0,
                        random_state=RANDOM_STATE,
                        n_jobs=-1,
                        verbosity=-1,
                    ),
                ),
            ]
        )
        model.fit(train_matrix, residual_target)
        predictions.append(model.predict(test_matrix) + baseline)
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
    combined, blocks = _assemble_v13_features(
        dataset_path=dataset_path,
        heat_targets_path=heat_targets_path,
        samples_path=samples_path,
        catalog_path=catalog_path,
        temporal_dir=temporal_dir,
    )
    groups = _group_feature_candidates(combined, blocks, catalog_path)
    base_features = _base_visible_features(combined)
    print(
        json.dumps(
            {
                "stage": "features_ready",
                "rows": len(combined),
                "groups": {
                    name: len(columns)
                    for name, columns in groups.items()
                },
                "base_visible_features": len(base_features),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    fold_materials: dict[str, Any] = {}
    for fold_name, (train_mask, evaluation_mask) in _fold_definitions(
        combined
    ).items():
        train = combined.loc[train_mask]
        evaluation = combined.loc[evaluation_mask]
        fallback = float(train[TARGET].median())
        train_baseline = _history_baseline(
            train, fallback=fallback
        ).to_numpy(float)
        evaluation_baseline = _history_baseline(
            evaluation, fallback=fallback
        ).to_numpy(float)
        residual = train[TARGET].to_numpy(float) - train_baseline
        train_factors, evaluation_factors, _, audit = (
            _fit_latent_factors(
                train, evaluation, residual, groups
            )
        )
        fold_materials[fold_name] = {
            "train": train,
            "evaluation": evaluation,
            "residual": residual,
            "evaluation_baseline": evaluation_baseline,
            "train_factors": train_factors,
            "evaluation_factors": evaluation_factors,
            "audit": audit,
        }
        print(
            json.dumps(
                {"stage": "fold_factors_ready", "fold": fold_name},
                ensure_ascii=False,
            ),
            flush=True,
        )

    candidates: list[dict[str, Any]] = []
    factories = _candidate_factories()
    for components in (1, 2, 3):
        for model_name, factory in factories.items():
            folds: dict[str, dict[str, float]] = {}
            for fold_name, material in fold_materials.items():
                train_matrix, _ = _design_matrix(
                    material["train"],
                    material["train_factors"],
                    base_features,
                    components,
                )
                evaluation_matrix, _ = _design_matrix(
                    material["evaluation"],
                    material["evaluation_factors"],
                    base_features,
                    components,
                )
                model = factory()
                model.fit(train_matrix, material["residual"])
                prediction = (
                    model.predict(evaluation_matrix)
                    + material["evaluation_baseline"]
                )
                folds[fold_name] = metrics(
                    material["evaluation"][TARGET].to_numpy(float),
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
                "candidate": f"latent_c{components}__{model_name}",
                "components_per_group": components,
                "model_name": model_name,
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
            item["max_fold_mae"],
        ),
    )

    train_mask = combined["experiment_split"].eq("train")
    test_mask = combined["experiment_split"].eq("test")
    train = combined.loc[train_mask]
    test = combined.loc[test_mask].copy()
    fallback = float(train[TARGET].median())
    train_baseline = _history_baseline(
        train, fallback=fallback
    ).to_numpy(float)
    test_baseline = _history_baseline(
        test, fallback=fallback
    ).to_numpy(float)
    residual = train[TARGET].to_numpy(float) - train_baseline
    train_factors, test_factors, transformers, factor_audit = (
        _fit_latent_factors(train, test, residual, groups)
    )
    train_matrix, downstream_features = _design_matrix(
        train,
        train_factors,
        base_features,
        selected["components_per_group"],
    )
    test_matrix, _ = _design_matrix(
        test,
        test_factors,
        base_features,
        selected["components_per_group"],
    )
    model = factories[selected["model_name"]]()
    model.fit(train_matrix, residual)
    prediction = model.predict(test_matrix) + test_baseline
    test_metrics = metrics(test[TARGET].to_numpy(float), prediction)
    distribution, distribution_models = _fit_quantile_models(
        train_matrix, test_matrix, residual, test_baseline
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
            "group_transformers": transformers,
            "base_features": base_features,
            "downstream_features": downstream_features,
            "components_per_group": selected["components_per_group"],
            "model": model,
            "distribution_models": distribution_models,
            "fallback": fallback,
            "status": "experimental_offline_v14",
        },
        models_dir / "selected_v14.joblib",
    )
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v14",
        "selection_contract": (
            "process-group feature ranking, imputation, scaling and PLS "
            "residual factors fit inside each April/May/June training fold; "
            "July historical test read after selection"
        ),
        "pareto_policy": {
            "robust_mae_tolerance": 0.00015,
            "pool_size": len(pareto_pool),
            "secondary_objective": "mean_hit_rate_abs_le_002",
        },
        "selected": {
            **selected,
            "base_feature_count": len(base_features),
            "latent_feature_count": (
                len(downstream_features) - len(base_features)
            ),
            "historical_test": test_metrics,
            "distribution_test": distribution_metrics,
        },
        "candidate_ranking": ranking,
        "joint_task_readiness": {
            "si_distribution_head": "trained_experimental_offline_v14",
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
        output_dir / "factor_audit.json",
        {
            "folds": {
                name: material["audit"]
                for name, material in fold_materials.items()
            },
            "final_train": factor_audit,
        },
    )
    _write_json(
        output_dir / "feature_contract.json",
        {
            "process_groups": {
                name: len(columns) for name, columns in groups.items()
            },
            "top_k_per_group": TOP_K_PER_GROUP,
            "maximum_components_per_group": MAX_COMPONENTS,
            "base_visible_features": base_features,
            "downstream_features": downstream_features,
            "latent_target": "Si residual from prior-published history baseline",
            "all_transformers_training_fold_only": True,
            "all_features_strictly_before_cutoff": True,
            "taphole_temperature_is_proxy_only": True,
        },
    )
    report = [
        "# V14 工艺分组潜在热状态因子报告",
        "",
        f"- 选中候选：`{selected['candidate']}`",
        f"- 预测试稳健分数：{selected['robust_mae_score']:.6f}",
        f"- 基础可见历史/化验特征：{len(base_features)}",
        (
            f"- 潜在热状态因子："
            f"{len(downstream_features) - len(base_features)}"
        ),
        (
            f"- 历史MAE / ±0.02 / ±0.05："
            f"{test_metrics['mae']:.6f} / "
            f"{test_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        "",
        "- 真实铁水温度标签仍缺失，PLS因子只针对Si历史残差。",
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
            "xgboost": xgboost.__version__,
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
        description="训练V14工艺分组潜在热状态因子模型。"
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
    selected = run_experiment(
        dataset_path=args.dataset,
        heat_targets_path=args.heat_targets,
        samples_path=args.samples,
        catalog_path=args.sensor_catalog,
        temporal_dir=args.temporal_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(selected, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
