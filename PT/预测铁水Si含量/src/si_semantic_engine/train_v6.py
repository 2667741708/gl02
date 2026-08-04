"""Train V6 heat-state semantic and residual Si candidates.

V6 adds three changes over V5:

* short/long-window divergence and direction-persistence neurons;
* explicit thermal-input, permeability and spatial heat-state neurons;
* leakage-safe residual learning against previously published Si history,
  optionally with recency weighting for operating-regime drift.

The true hot-metal-temperature head is deliberately gated when no trustworthy
temperature label with a real measurement time is present.

Requirement:
    REQ-SI-THERMAL-STATE-V6-20260727
"""

from __future__ import annotations

import argparse
import json
import math
import platform
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from xgboost import XGBRegressor

from .formal_dataset import sha256_file
from .train_v3 import TARGET
from .train_v4 import _feature_sets
from .v4_features import build_v4_feature_blocks
from .v5_features import (
    derive_temporal_spatial_neurons,
    load_temporal_statistics,
    pivot_temporal_statistics,
    select_train_correlated_features,
)
from .v6_features import (
    attach_published_chemistry_history,
    derive_heat_state_neurons,
    derive_multiscale_neurons,
    select_best_window_features,
)


REQUIREMENT_ID = "REQ-SI-THERMAL-STATE-V6-20260727"
RANDOM_STATE = 20260727
TEMPERATURE_TARGET_CANDIDATES = (
    "target__hot_metal_temperature_c",
    "hot_metal_temperature_c",
    "tappingtemp",
)
HISTORY_BASELINE_COLUMNS = (
    "history_v4__Si_ewma_hl4",
    "history_v4__Si_ewma_hl8",
    "history_v4__Si_w12__median",
    "history_v4__Si_w24__median",
    "history_v4__Si_lag_1",
    "history__previous_Si_median_6",
    "history__previous_Si_1",
)


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str
    target_mode: str
    recency_half_life_days: float | None = None


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _artifact_hashes(directory: Path) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        if path.name in {"run_manifest.json", "sha256sums.json"}:
            continue
        output[path.relative_to(directory).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return output


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    residual = np.asarray(predicted, dtype=float) - np.asarray(
        actual, dtype=float
    )
    return {
        "rows": int(len(actual)),
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "bias": float(np.mean(residual)),
        "hit_rate_abs_le_002": float(np.mean(np.abs(residual) <= 0.02)),
        "hit_rate_abs_le_003": float(np.mean(np.abs(residual) <= 0.03)),
        "hit_rate_abs_le_004": float(np.mean(np.abs(residual) <= 0.04)),
        "hit_rate_abs_le_005": float(np.mean(np.abs(residual) <= 0.05)),
        "hit_rate_abs_le_010": float(np.mean(np.abs(residual) <= 0.10)),
    }


def _model(spec: ModelSpec) -> Pipeline:
    if spec.family == "extra_leaf2_f050":
        estimator: Any = ExtraTreesRegressor(
            n_estimators=320,
            min_samples_leaf=2,
            max_features=0.50,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    elif spec.family == "extra_leaf5_f070":
        estimator = ExtraTreesRegressor(
            n_estimators=320,
            min_samples_leaf=5,
            max_features=0.70,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    elif spec.family == "extra_leaf10_f100":
        estimator = ExtraTreesRegressor(
            n_estimators=320,
            min_samples_leaf=10,
            max_features=1.0,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    elif spec.family == "xgb_depth2":
        estimator = XGBRegressor(
            n_estimators=500,
            max_depth=2,
            learning_rate=0.025,
            min_child_weight=15.0,
            subsample=0.85,
            colsample_bytree=0.55,
            reg_alpha=0.05,
            reg_lambda=8.0,
            objective="reg:squarederror",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    elif spec.family == "xgb_depth3":
        estimator = XGBRegressor(
            n_estimators=450,
            max_depth=3,
            learning_rate=0.02,
            min_child_weight=18.0,
            subsample=0.85,
            colsample_bytree=0.45,
            reg_alpha=0.10,
            reg_lambda=10.0,
            objective="reg:squarederror",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    elif spec.family == "hist_leaf15":
        estimator = HistGradientBoostingRegressor(
            loss="absolute_error",
            learning_rate=0.035,
            max_iter=450,
            max_leaf_nodes=15,
            min_samples_leaf=25,
            l2_regularization=8.0,
            random_state=RANDOM_STATE,
        )
    else:
        raise ValueError(f"未知模型族：{spec.family}")
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("model", estimator),
        ]
    )


def _recency_weights(
    timestamps: pd.Series,
    half_life_days: float | None,
) -> np.ndarray | None:
    if half_life_days is None:
        return None
    values = pd.to_datetime(timestamps, errors="raise")
    age_days = (
        values.max() - values
    ).dt.total_seconds().to_numpy(float) / 86400.0
    weights = np.power(0.5, age_days / float(half_life_days))
    return np.clip(weights, 0.05, 1.0)


def _history_baseline(
    frame: pd.DataFrame,
    *,
    fallback: float,
) -> pd.Series:
    available = [
        column for column in HISTORY_BASELINE_COLUMNS if column in frame
    ]
    if not available:
        return pd.Series(fallback, index=frame.index, dtype=float)
    values = frame[available].apply(pd.to_numeric, errors="coerce")
    baseline = values.bfill(axis=1).iloc[:, 0]
    return baseline.fillna(float(fallback)).astype(float)


def _fit_candidate(
    spec: ModelSpec,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: Sequence[str],
    *,
    fallback: float,
) -> tuple[Pipeline, np.ndarray]:
    model = _model(spec)
    train_baseline = _history_baseline(train, fallback=fallback)
    validation_baseline = _history_baseline(validation, fallback=fallback)
    target = train[TARGET].to_numpy(float)
    if spec.target_mode == "residual":
        target = target - train_baseline.to_numpy(float)
    elif spec.target_mode != "direct":
        raise ValueError(f"未知目标模式：{spec.target_mode}")
    weights = _recency_weights(
        train["prediction_cutoff_ts"], spec.recency_half_life_days
    )
    fit_kwargs = (
        {"model__sample_weight": weights}
        if weights is not None
        else {}
    )
    model.fit(train[list(features)], target, **fit_kwargs)
    prediction = model.predict(validation[list(features)])
    if spec.target_mode == "residual":
        prediction = prediction + validation_baseline.to_numpy(float)
    return model, np.asarray(prediction, dtype=float)


def _predict_candidate(
    model: Pipeline,
    spec: ModelSpec,
    frame: pd.DataFrame,
    features: Sequence[str],
    *,
    fallback: float,
) -> np.ndarray:
    prediction = model.predict(frame[list(features)])
    if spec.target_mode == "residual":
        prediction = prediction + _history_baseline(
            frame, fallback=fallback
        ).to_numpy(float)
    return np.asarray(prediction, dtype=float)


def _importance_features(
    train: pd.DataFrame,
    candidates: Sequence[str],
    *,
    top_k: int,
) -> list[str]:
    numeric = train[list(candidates)].apply(
        pd.to_numeric, errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)
    coverage = numeric.notna().mean()
    usable = coverage.index[
        (coverage >= 0.50) & (numeric.nunique(dropna=True) > 1)
    ].tolist()
    imputer = SimpleImputer(strategy="median")
    values = imputer.fit_transform(numeric[usable])
    selector = ExtraTreesRegressor(
        n_estimators=240,
        min_samples_leaf=5,
        max_features=0.70,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    selector.fit(values, train[TARGET].to_numpy(float))
    order = np.argsort(selector.feature_importances_)[::-1]
    return [usable[index] for index in order[: min(top_k, len(order))]]


def _feature_recipes(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    *,
    base_history: Sequence[str],
    temporal_columns: Sequence[str],
    multiscale_columns: Sequence[str],
    heat_state_columns: Sequence[str],
    spatial_columns: Sequence[str],
    chemistry_columns: Sequence[str],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    train = combined.loc[train_mask]
    optimal_windows, optimal_audit = select_best_window_features(
        train, train[TARGET], temporal_columns
    )
    derived_candidates = list(
        dict.fromkeys(
            [
                *multiscale_columns,
                *heat_state_columns,
                *spatial_columns,
            ]
        )
    )
    derived_ranked, derived_ranking = select_train_correlated_features(
        train,
        train[TARGET],
        derived_candidates,
        top_k=len(derived_candidates),
    )
    base_importance250 = _importance_features(
        train, base_history, top_k=250
    )
    recipes = {
        "base_history": list(base_history),
        "base_importance250": base_importance250,
        "base_plus_optimal_windows": list(
            dict.fromkeys([*base_history, *optimal_windows])
        ),
        "base_plus_heat_state100": list(
            dict.fromkeys([*base_history, *derived_ranked[:100]])
        ),
        "base_plus_heat_state250": list(
            dict.fromkeys([*base_history, *derived_ranked[:250]])
        ),
        "base_plus_chemistry": list(
            dict.fromkeys([*base_history, *chemistry_columns])
        ),
        "base_chemistry_heat250": list(
            dict.fromkeys(
                [*base_history, *chemistry_columns, *derived_ranked[:250]]
            )
        ),
        "base_optimal_heat250": list(
            dict.fromkeys(
                [*base_history, *optimal_windows, *derived_ranked[:250]]
            )
        ),
    }
    return recipes, {
        "selection_scope": "training_split_only",
        "training_rows": int(train_mask.sum()),
        "optimal_window_feature_count": len(optimal_windows),
        "optimal_window_audit": optimal_audit,
        "derived_eligible_count": len(derived_ranked),
        "chemistry_feature_count": len(chemistry_columns),
        "derived_ranking_top300": derived_ranking.head(300).to_dict(
            "records"
        ),
        "recipe_counts": {
            name: len(features) for name, features in recipes.items()
        },
    }


def _specs_for_recipe(recipe: str) -> list[ModelSpec]:
    specs = [
        ModelSpec(
            name="extra2_direct",
            family="extra_leaf2_f050",
            target_mode="direct",
        ),
        ModelSpec(
            name="extra2_residual",
            family="extra_leaf2_f050",
            target_mode="residual",
        ),
        ModelSpec(
            name="extra5_residual",
            family="extra_leaf5_f070",
            target_mode="residual",
        ),
        ModelSpec(
            name="extra10_residual",
            family="extra_leaf10_f100",
            target_mode="residual",
        ),
        ModelSpec(
            name="extra5_residual_decay90",
            family="extra_leaf5_f070",
            target_mode="residual",
            recency_half_life_days=90.0,
        ),
    ]
    if recipe in {
        "base_history",
        "base_importance250",
        "base_plus_heat_state250",
        "base_plus_chemistry",
        "base_chemistry_heat250",
        "base_optimal_heat250",
    }:
        specs.extend(
            [
                ModelSpec(
                    name="xgb2_direct",
                    family="xgb_depth2",
                    target_mode="direct",
                ),
                ModelSpec(
                    name="xgb2_residual",
                    family="xgb_depth2",
                    target_mode="residual",
                ),
                ModelSpec(
                    name="xgb3_residual_decay90",
                    family="xgb_depth3",
                    target_mode="residual",
                    recency_half_life_days=90.0,
                ),
                ModelSpec(
                    name="hist15_residual",
                    family="hist_leaf15",
                    target_mode="residual",
                ),
            ]
        )
    return specs


def _selection_key(item: dict[str, Any]) -> tuple[Any, ...]:
    score = item["metrics"]
    return (
        score["mae"],
        -score["hit_rate_abs_le_002"],
        score["rmse"],
        item["candidate"],
    )


def _stability_selection_key(item: dict[str, Any]) -> tuple[Any, ...]:
    score = item["pretest_stability"]
    return (
        score["robust_mae_score"],
        score["max_fold_mae"],
        -score["mean_hit_rate_abs_le_002"],
        item["metrics"]["mae"],
        item["candidate"],
    )


def _select_with_pretest_stability(
    combined: pd.DataFrame,
    validation_results: Sequence[dict[str, Any]],
    fitted: dict[str, tuple[Pipeline, ModelSpec, list[str]]],
    *,
    base_history: Sequence[str],
    temporal_columns: Sequence[str],
    multiscale_columns: Sequence[str],
    heat_state_columns: Sequence[str],
    spatial_columns: Sequence[str],
    chemistry_columns: Sequence[str],
    finalist_count: int = 12,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Choose finalists using April/May walk-forward plus June validation."""

    finalists = sorted(validation_results, key=_selection_key)[
        :finalist_count
    ]
    fold_cache: dict[str, tuple[pd.Series, pd.Series, dict[str, list[str]]]] = {}
    for month in ("2026-04", "2026-05"):
        train_mask = combined["prediction_month"].lt(month)
        test_mask = combined["prediction_month"].eq(month)
        if int(train_mask.sum()) < 500 or int(test_mask.sum()) < 10:
            continue
        recipes, _ = _feature_recipes(
            combined,
            train_mask,
            base_history=base_history,
            temporal_columns=temporal_columns,
            multiscale_columns=multiscale_columns,
            heat_state_columns=heat_state_columns,
            spatial_columns=spatial_columns,
            chemistry_columns=chemistry_columns,
        )
        fold_cache[month] = (train_mask, test_mask, recipes)

    audited: list[dict[str, Any]] = []
    for finalist in finalists:
        _, spec, _ = fitted[finalist["candidate"]]
        fold_metrics: dict[str, dict[str, float]] = {
            "2026-06_fixed_validation": finalist["metrics"]
        }
        for month, (train_mask, test_mask, recipes) in fold_cache.items():
            features = recipes[finalist["recipe"]]
            train = combined.loc[train_mask]
            test = combined.loc[test_mask]
            fallback = float(train[TARGET].median())
            model, prediction = _fit_candidate(
                spec,
                train,
                test,
                features,
                fallback=fallback,
            )
            del model
            fold_metrics[month] = metrics(
                test[TARGET].to_numpy(float), prediction
            )
        maes = np.asarray(
            [item["mae"] for item in fold_metrics.values()], dtype=float
        )
        hit_rates = np.asarray(
            [
                item["hit_rate_abs_le_002"]
                for item in fold_metrics.values()
            ],
            dtype=float,
        )
        stability = {
            "folds": fold_metrics,
            "mean_mae": float(np.mean(maes)),
            "std_mae": float(np.std(maes, ddof=0)),
            "max_fold_mae": float(np.max(maes)),
            "mean_hit_rate_abs_le_002": float(np.mean(hit_rates)),
            "robust_mae_score": float(
                np.mean(maes) + 0.50 * np.std(maes, ddof=0)
            ),
        }
        audited.append({**finalist, "pretest_stability": stability})
    selected = min(audited, key=_stability_selection_key)
    return selected, sorted(audited, key=_stability_selection_key)


def _temperature_label_audit(
    frame: pd.DataFrame,
    heat_targets: pd.DataFrame,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "required_contract": (
            "true hot-metal measurement, official meltno, real "
            "measurement timestamp, taphole/tank/stage"
        ),
        "taphole_proxy_policy": (
            "T_taphole_1/2 are auxiliary features only, never labels"
        ),
        "candidates": {},
    }
    usable = 0
    for column in TEMPERATURE_TARGET_CANDIDATES:
        source = frame if column in frame else heat_targets
        count = (
            int(pd.to_numeric(source[column], errors="coerce").notna().sum())
            if column in source
            else 0
        )
        result["candidates"][column] = count
        usable = max(usable, count)
    result["usable_label_rows"] = usable
    result["temperature_head_status"] = (
        "ready_for_training"
        if usable > 0
        else "blocked_no_true_hot_metal_temperature_label"
    )
    result["thermal_state_probability_head_status"] = (
        "blocked_until_true_temperature_label"
        if usable == 0
        else "requires_joint_training"
    )
    return result


def _distribution_models(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: Sequence[str],
    *,
    fallback: float,
    target_mode: str,
) -> tuple[dict[float, Pipeline], np.ndarray]:
    top_features = _importance_features(train, features, top_k=300)
    train_baseline = _history_baseline(train, fallback=fallback)
    test_baseline = _history_baseline(test, fallback=fallback)
    target = train[TARGET].to_numpy(float)
    if target_mode == "residual":
        target = target - train_baseline.to_numpy(float)
    models: dict[float, Pipeline] = {}
    predictions: list[np.ndarray] = []
    for quantile in (0.10, 0.50, 0.90):
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        loss="quantile",
                        quantile=quantile,
                        learning_rate=0.035,
                        max_iter=450,
                        max_leaf_nodes=15,
                        min_samples_leaf=25,
                        l2_regularization=8.0,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        )
        model.fit(train[top_features], target)
        prediction = model.predict(test[top_features])
        if target_mode == "residual":
            prediction = prediction + test_baseline.to_numpy(float)
        models[quantile] = model
        predictions.append(np.asarray(prediction, dtype=float))
    ordered = np.sort(np.vstack(predictions), axis=0)
    return models, ordered


def _rolling_month_backtest(
    combined: pd.DataFrame,
    *,
    base_history: Sequence[str],
    temporal_columns: Sequence[str],
    multiscale_columns: Sequence[str],
    heat_state_columns: Sequence[str],
    spatial_columns: Sequence[str],
    chemistry_columns: Sequence[str],
    selected_recipe: str,
    selected_spec: ModelSpec,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for target_month in combined["prediction_month"].drop_duplicates():
        test_mask = combined["prediction_month"].eq(target_month)
        train_mask = combined["prediction_month"].lt(target_month)
        if int(train_mask.sum()) < 500 or int(test_mask.sum()) < 10:
            continue
        recipes, _ = _feature_recipes(
            combined,
            train_mask,
            base_history=base_history,
            temporal_columns=temporal_columns,
            multiscale_columns=multiscale_columns,
            heat_state_columns=heat_state_columns,
            spatial_columns=spatial_columns,
            chemistry_columns=chemistry_columns,
        )
        features = recipes[selected_recipe]
        train = combined.loc[train_mask]
        test = combined.loc[test_mask]
        fallback = float(train[TARGET].median())
        model, prediction = _fit_candidate(
            selected_spec,
            train,
            test,
            features,
            fallback=fallback,
        )
        del model
        output[str(target_month)] = {
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "feature_count": len(features),
            "train_end": str(train["prediction_cutoff_ts"].max()),
            "test_start": str(test["prediction_cutoff_ts"].min()),
            "metrics": metrics(test[TARGET].to_numpy(float), prediction),
        }
    return output


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
    frame = pd.read_csv(
        dataset_path, low_memory=False, encoding="utf-8-sig"
    )
    heat_targets = pd.read_csv(
        heat_targets_path, low_memory=False, encoding="utf-8-sig"
    )
    samples = pd.read_csv(
        samples_path, low_memory=False, encoding="utf-8-sig"
    )
    frame["prediction_cutoff_ts"] = pd.to_datetime(
        frame["prediction_cutoff_ts"], errors="raise"
    )
    frame["prediction_month"] = frame[
        "prediction_cutoff_ts"
    ].dt.to_period("M").astype(str)
    v4_blocks, v4_audit = build_v4_feature_blocks(
        frame, heat_targets, catalog_path
    )
    temporal_long, temporal_manifest = load_temporal_statistics(
        temporal_dir
    )
    windows = tuple(
        int(value)
        for value in temporal_manifest["feature_contract"][
            "windows_minutes"
        ]
    )
    temporal, temporal_audit = pivot_temporal_statistics(
        temporal_long, frame, windows_minutes=windows
    )
    spatial = derive_temporal_spatial_neurons(
        temporal, windows_minutes=windows
    )
    multiscale = derive_multiscale_neurons(temporal)
    heat_state = derive_heat_state_neurons(temporal)
    chemistry_history, chemistry_audit = (
        attach_published_chemistry_history(frame, samples)
    )
    combined = pd.concat(
        [
            frame,
            *v4_blocks.values(),
            temporal,
            spatial,
            multiscale,
            heat_state,
            chemistry_history,
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan)
    train_mask = combined["experiment_split"].eq("train")
    validation_mask = combined["experiment_split"].eq("validation")
    test_mask = combined["experiment_split"].eq("test")
    v4_feature_sets, _ = _feature_sets(
        combined,
        train_mask,
        {name: list(block.columns) for name, block in v4_blocks.items()},
    )
    base_history = v4_feature_sets["v3_plus_history"]
    recipes, selection_audit = _feature_recipes(
        combined,
        train_mask,
        base_history=base_history,
        temporal_columns=list(temporal.columns),
        multiscale_columns=list(multiscale.columns),
        heat_state_columns=list(heat_state.columns),
        spatial_columns=list(spatial.columns),
        chemistry_columns=list(chemistry_history.columns),
    )

    train = combined.loc[train_mask]
    validation = combined.loc[validation_mask]
    fallback = float(train[TARGET].median())
    validation_results: list[dict[str, Any]] = []
    fitted: dict[str, tuple[Pipeline, ModelSpec, list[str]]] = {}
    for recipe, features in recipes.items():
        for spec in _specs_for_recipe(recipe):
            candidate = f"{recipe}__{spec.name}"
            model, prediction = _fit_candidate(
                spec,
                train,
                validation,
                features,
                fallback=fallback,
            )
            record = {
                "candidate": candidate,
                "recipe": recipe,
                "model": spec.name,
                "family": spec.family,
                "target_mode": spec.target_mode,
                "recency_half_life_days": spec.recency_half_life_days,
                "feature_count": len(features),
                "metrics": metrics(
                    validation[TARGET].to_numpy(float), prediction
                ),
            }
            validation_results.append(record)
            fitted[candidate] = (model, spec, features)
    selected, stability_audit = _select_with_pretest_stability(
        combined,
        validation_results,
        fitted,
        base_history=base_history,
        temporal_columns=list(temporal.columns),
        multiscale_columns=list(multiscale.columns),
        heat_state_columns=list(heat_state.columns),
        spatial_columns=list(spatial.columns),
        chemistry_columns=list(chemistry_history.columns),
    )
    selected_model, selected_spec, selected_features = fitted[
        selected["candidate"]
    ]
    test = combined.loc[test_mask].copy()
    test_prediction = _predict_candidate(
        selected_model,
        selected_spec,
        test,
        selected_features,
        fallback=fallback,
    )
    test_metrics = metrics(test[TARGET].to_numpy(float), test_prediction)

    distribution_models, distribution = _distribution_models(
        train,
        test,
        selected_features,
        fallback=fallback,
        target_mode=selected_spec.target_mode,
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
        "quantile_crossing_rows_after_sort": 0,
    }

    predictions = test[
        ["official_meltno", "prediction_cutoff_ts", TARGET]
    ].copy()
    predictions["prediction__Si_representative"] = test_prediction
    predictions["prediction__Si_p10"] = p10
    predictions["prediction__Si_p50"] = p50
    predictions["prediction__Si_p90"] = p90
    predictions["absolute_error"] = np.abs(
        predictions[TARGET]
        - predictions["prediction__Si_representative"]
    )
    predictions.to_csv(
        output_dir / "predictions_test.csv",
        index=False,
        encoding="utf-8-sig",
    )
    joblib.dump(
        {
            "model": selected_model,
            "features": selected_features,
            "spec": selected_spec,
            "candidate": selected["candidate"],
            "fallback": fallback,
            "status": "experimental_offline_v6",
        },
        models_dir / "selected_v6.joblib",
    )
    joblib.dump(
        {
            "models": distribution_models,
            "features": _importance_features(
                train, selected_features, top_k=300
            ),
            "target_mode": selected_spec.target_mode,
            "status": "experimental_offline_v6",
        },
        models_dir / "distribution_v6.joblib",
    )

    estimator = selected_model.named_steps["model"]
    feature_importance: list[dict[str, Any]] = []
    if hasattr(estimator, "feature_importances_"):
        feature_importance = sorted(
            [
                {"feature": feature, "importance": float(value)}
                for feature, value in zip(
                    selected_features, estimator.feature_importances_
                )
            ],
            key=lambda item: item["importance"],
            reverse=True,
        )
    _write_json(
        output_dir / "feature_importance.json",
        feature_importance[:300],
    )

    rolling = _rolling_month_backtest(
        combined,
        base_history=base_history,
        temporal_columns=list(temporal.columns),
        multiscale_columns=list(multiscale.columns),
        heat_state_columns=list(heat_state.columns),
        spatial_columns=list(spatial.columns),
        chemistry_columns=list(chemistry_history.columns),
        selected_recipe=selected["recipe"],
        selected_spec=selected_spec,
    )
    temperature_audit = _temperature_label_audit(frame, heat_targets)
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v6",
        "selection_contract": (
            "feature ranking uses each fold train only; finalists use April "
            "and May expanding folds plus fixed June validation; historical "
            "July test is read after selection but has been reused across "
            "versions and is not a fresh deployment-grade holdout"
        ),
        "feature_blocks": {
            "base_history": len(base_history),
            "temporal": len(temporal.columns),
            "spatial": len(spatial.columns),
            "multiscale": len(multiscale.columns),
            "heat_state": len(heat_state.columns),
            "chemistry_history": len(chemistry_history.columns),
            "windows_minutes": list(windows),
        },
        "validation_candidates": sorted(
            validation_results, key=_selection_key
        ),
        "pretest_stability_finalists": stability_audit,
        "selected": {
            **selected,
            "test": test_metrics,
            "distribution_test": distribution_metrics,
        },
        "rolling_month_backtest": rolling,
        "joint_task_readiness": {
            "si_distribution_head": "trained_experimental_offline_v6",
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
            "v4_derivation": v4_audit,
            "temporal_pivot": temporal_audit,
            "source_manifest_requirement": temporal_manifest[
                "requirement_id"
            ],
            "source_manifest_windows": list(windows),
            "derivation": {
                "multiscale_columns": len(multiscale.columns),
                "heat_state_columns": len(heat_state.columns),
                "spatial_columns": len(spatial.columns),
                "chemistry_history": chemistry_audit,
                "all_features_strictly_before_cutoff": True,
                "taphole_temperature_is_proxy_only": True,
                "cooling_wall_heat_loss_status": (
                    "not_in_current_133_point_catalog"
                ),
            },
        },
    )
    report = [
        "# V6 热状态语义神经元与残差学习报告",
        "",
        f"- 选中候选：`{selected['candidate']}`",
        f"- 特征数：{selected['feature_count']}",
        (
            f"- 验证 MAE / ±0.02："
            f"{selected['metrics']['mae']:.6f} / "
            f"{selected['metrics']['hit_rate_abs_le_002']:.2%}"
        ),
        (
            f"- 历史测试 MAE / ±0.02 / ±0.05："
            f"{test_metrics['mae']:.6f} / "
            f"{test_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        (
            f"- Si分布P50 MAE / P10-P90覆盖率："
            f"{distribution_metrics['p50']['mae']:.6f} / "
            f"{distribution_metrics['p10_p90_coverage']:.2%}"
        ),
        (
            "- 铁水温度任务："
            f"`{temperature_audit['temperature_head_status']}`"
        ),
        "",
        "- T_taphole_1/2仅作辅助代理特征，未作为铁水温度标签。",
        "- 当前133点目录不含冷却壁水温差/流量/热负荷，已明确记录缺口。",
        "- 历史测试已在多版本中复用，最终结论必须等待新的未来炉次盲测。",
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
        "selected_candidate": selected["candidate"],
        "selected_feature_count": len(selected_features),
        "artifacts": _artifact_hashes(output_dir),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_json(output_dir / "sha256sums.json", _artifact_hashes(output_dir))
    return result


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="训练V6热状态语义神经元与Si残差模型。"
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
