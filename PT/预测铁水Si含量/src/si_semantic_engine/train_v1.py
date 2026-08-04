"""Run the fixed V1 Si prediction experiment.

The script compares chronological baselines, distilled rule-feature models, a
full snapshot tree model and an interpretable semantic-neuron ensemble.

Requirement:
    REQ-SI-EXPERIMENT-V1-20260726
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy.special import expit
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .engine import SemanticSiEngine
from .experiment_data import TARGET_COLUMN, sha256_file


RANDOM_STATE = 20260726
TARGET_LOW = 0.20
TARGET_HIGH = 0.40
Z80 = 1.2815515655446004


def _safe_float(value: Any) -> float | None:
    number = float(value)
    return number if np.isfinite(number) else None


def _band_class(values: np.ndarray) -> np.ndarray:
    return np.where(
        values < TARGET_LOW,
        0,
        np.where(values > TARGET_HIGH, 2, 1),
    )


def regression_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
    residual_std: float | None = None,
) -> dict[str, Any]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    absolute_error = np.abs(actual - predicted)
    actual_class = _band_class(actual)
    predicted_class = _band_class(predicted)

    def recall(class_id: int) -> float | None:
        mask = actual_class == class_id
        if not mask.any():
            return None
        return float(np.mean(predicted_class[mask] == class_id))

    metrics: dict[str, Any] = {
        "rows": int(len(actual)),
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)),
        "hit_rate_abs_le_005": float(np.mean(absolute_error <= 0.05)),
        "hit_rate_abs_le_010": float(np.mean(absolute_error <= 0.10)),
        "target_band_class_accuracy": float(
            np.mean(actual_class == predicted_class)
        ),
        "low_si_recall": recall(0),
        "high_si_recall": recall(2),
        "actual_low_count": int(np.sum(actual_class == 0)),
        "actual_target_count": int(np.sum(actual_class == 1)),
        "actual_high_count": int(np.sum(actual_class == 2)),
    }
    if residual_std is not None:
        low = predicted - Z80 * residual_std
        high = predicted + Z80 * residual_std
        metrics["residual_std_from_validation"] = float(residual_std)
        metrics["p10_p90_coverage"] = float(
            np.mean((actual >= low) & (actual <= high))
        )
        metrics["p10_p90_average_width"] = float(np.mean(high - low))
    return metrics


def _candidate_columns(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    history = [
        column
        for column in frame.columns
        if column.startswith("history__previous_")
    ]
    diagnostics = [
        column
        for column in (
            "diagnosis__main_score",
            "diagnosis__main_confidence",
            "diagnosis__secondary_score",
            "diagnosis__secondary_confidence",
            "diagnosis__coverage_ratio",
            "diagnosis__missing_variable_count",
        )
        if column in frame.columns
    ]
    rule = [
        column
        for column in frame.columns
        if column.startswith("feature__") or column.startswith("score__")
    ]
    rule_columns = list(dict.fromkeys(rule + diagnostics + history))
    sensor_columns = [
        column
        for column in frame.columns
        if column.startswith("sensor__")
        and column
        not in {
            "sensor__available_count",
            "sensor__missing_count",
            "sensor__bad_quality_count",
            "sensor__unknown_quality_count",
            "sensor__max_age_seconds",
        }
    ]
    full_columns = list(dict.fromkeys(rule_columns + sensor_columns))
    return rule_columns, full_columns


def _numeric_frame(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    return frame.loc[:, list(columns)].apply(pd.to_numeric, errors="coerce")


def _usable_columns(
    train_frame: pd.DataFrame,
    candidates: Sequence[str],
    minimum_non_missing: int = 20,
) -> list[str]:
    numeric = _numeric_frame(train_frame, candidates)
    output: list[str] = []
    for column in numeric.columns:
        series = numeric[column]
        if int(series.notna().sum()) < minimum_non_missing:
            continue
        if int(series.nunique(dropna=True)) <= 1:
            continue
        output.append(column)
    return output


def _ridge_pipeline(row_count: int) -> Pipeline:
    splits = min(5, max(2, row_count // 100))
    return Pipeline(
        [
            (
                "imputer",
                SimpleImputer(strategy="median", keep_empty_features=True),
            ),
            ("scaler", StandardScaler()),
            (
                "model",
                RidgeCV(
                    alphas=np.logspace(-4, 4, 17),
                    cv=TimeSeriesSplit(n_splits=splits),
                ),
            ),
        ]
    )


def _hist_gradient_pipeline() -> Pipeline:
    return Pipeline(
        [
            (
                "imputer",
                SimpleImputer(strategy="median", keep_empty_features=True),
            ),
            (
                "model",
                HistGradientBoostingRegressor(
                    learning_rate=0.035,
                    max_iter=350,
                    max_leaf_nodes=15,
                    min_samples_leaf=20,
                    l2_regularization=1.0,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def _extra_trees_pipeline() -> Pipeline:
    return Pipeline(
        [
            (
                "imputer",
                SimpleImputer(strategy="median", keep_empty_features=True),
            ),
            (
                "model",
                ExtraTreesRegressor(
                    n_estimators=400,
                    min_samples_leaf=5,
                    max_features=0.65,
                    n_jobs=1,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def semantic_feature_groups(columns: Sequence[str]) -> dict[str, list[str]]:
    groups = {
        "thermal_input": [],
        "permeability": [],
        "gas_flow_distribution": [],
        "charging_and_level": [],
        "diagnosis_state": [],
        "previous_heat_inertia": [],
    }
    for column in columns:
        lower = column.lower()
        if lower.startswith("history__previous_"):
            groups["previous_heat_inertia"].append(column)
        elif lower.startswith("score__") or lower.startswith("diagnosis__"):
            groups["diagnosis_state"].append(column)
        elif any(
            token in lower
            for token in (
                "t_blast",
                "tft",
                "q_o2",
                "o2_intensity",
                "pci",
                "t_taphole",
            )
        ):
            groups["thermal_input"].append(column)
        elif any(
            token in lower
            for token in (
                "dp_",
                "z60_pi",
                "zstd_pi",
                "q_blast",
                "p_blast",
                "p_top",
                "high_pressure",
            )
        ):
            groups["permeability"].append(column)
        elif any(
            token in lower
            for token in (
                "t_top",
                "disp",
                "body",
                "sector",
                "hotdev",
                "hotspot",
                "spiketop",
                "g_body",
            )
        ):
            groups["gas_flow_distribution"].append(column)
        elif any(
            token in lower
            for token in (
                "deltal",
                "l_current",
                "l_diff",
                "l_effective",
                "l_slope",
                "dropbatch",
                "charge_",
                "probe_",
                "lowline",
            )
        ):
            groups["charging_and_level"].append(column)
    return {name: values for name, values in groups.items() if values}


def _semantic_inner_pipeline() -> Pipeline:
    return Pipeline(
        [
            (
                "imputer",
                SimpleImputer(strategy="median", keep_empty_features=True),
            ),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ]
    )


def fit_semantic_model(
    train_frame: pd.DataFrame,
    target: np.ndarray,
    groups: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    group_names = list(groups)
    row_count = len(train_frame)
    oof = np.full((row_count, len(group_names)), np.nan, dtype=float)
    splitter = TimeSeriesSplit(n_splits=5)
    for fit_index, holdout_index in splitter.split(train_frame):
        for group_index, group_name in enumerate(group_names):
            columns = list(groups[group_name])
            model = _semantic_inner_pipeline()
            model.fit(
                _numeric_frame(train_frame.iloc[fit_index], columns),
                target[fit_index],
            )
            oof[holdout_index, group_index] = model.predict(
                _numeric_frame(train_frame.iloc[holdout_index], columns)
            )
    valid = np.isfinite(oof).all(axis=1)
    if int(valid.sum()) < 100:
        raise ValueError("语义神经元折外训练样本不足100")
    thresholds = np.median(oof[valid], axis=0)
    scales = np.std(oof[valid], axis=0, ddof=1)
    scales = np.maximum(scales, 0.01)
    activations = expit((oof[valid] - thresholds) / scales)
    outer = RidgeCV(
        alphas=np.logspace(-4, 3, 15),
        cv=TimeSeriesSplit(n_splits=3),
    )
    outer.fit(activations, target[valid])
    final_models: dict[str, Pipeline] = {}
    for group_name in group_names:
        columns = list(groups[group_name])
        model = _semantic_inner_pipeline()
        model.fit(_numeric_frame(train_frame, columns), target)
        final_models[group_name] = model
    return {
        "group_names": group_names,
        "groups": {name: list(groups[name]) for name in group_names},
        "thresholds": thresholds,
        "scales": scales,
        "outer_model": outer,
        "inner_models": final_models,
        "oof_valid_rows": int(valid.sum()),
        "oof_total_rows": int(row_count),
    }


def predict_semantic(
    model: Mapping[str, Any], frame: pd.DataFrame
) -> np.ndarray:
    responses = []
    for group_name in model["group_names"]:
        columns = model["groups"][group_name]
        responses.append(
            model["inner_models"][group_name].predict(
                _numeric_frame(frame, columns)
            )
        )
    response_matrix = np.column_stack(responses)
    activations = expit(
        (response_matrix - model["thresholds"]) / model["scales"]
    )
    return np.asarray(model["outer_model"].predict(activations), dtype=float)


def export_semantic_engine(
    model: Mapping[str, Any],
    residual_std: float,
    model_version: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    outer = model["outer_model"]
    output_weights = np.asarray(outer.coef_, dtype=float)
    engine_intercept = float(outer.intercept_) + 0.5 * float(
        output_weights.sum()
    )
    neurons = []
    feature_contract: dict[str, Any] = {}
    direction = {
        "thermal_input": "expert_expected_positive_tendency_unconstrained_v1",
        "permeability": "non_monotonic_unconstrained_v1",
        "gas_flow_distribution": "interaction_and_stability_unconstrained_v1",
        "charging_and_level": "non_monotonic_unconstrained_v1",
        "diagnosis_state": "derived_rule_state_unconstrained_v1",
        "previous_heat_inertia": "expert_expected_positive_unconstrained_v1",
    }
    display = {
        "thermal_input": "热输入",
        "permeability": "透气性与压差",
        "gas_flow_distribution": "煤气流与炉体分布",
        "charging_and_level": "料线与装料状态",
        "diagnosis_state": "现有炉况诊断",
        "previous_heat_inertia": "前序炉Si惯性",
    }
    for index, group_name in enumerate(model["group_names"]):
        pipeline = model["inner_models"][group_name]
        imputer: SimpleImputer = pipeline.named_steps["imputer"]
        scaler: StandardScaler = pipeline.named_steps["scaler"]
        ridge: Ridge = pipeline.named_steps["model"]
        columns = model["groups"][group_name]
        feature_weights = {}
        for feature_index, source_name in enumerate(columns):
            standardized_name = f"z__{source_name}"
            feature_weights[standardized_name] = float(
                np.asarray(ridge.coef_)[feature_index]
            )
            feature_contract[source_name] = {
                "standardized_name": standardized_name,
                "impute_median": _safe_float(
                    imputer.statistics_[feature_index]
                ),
                "train_mean_after_imputation": _safe_float(
                    scaler.mean_[feature_index]
                ),
                "train_scale_after_imputation": _safe_float(
                    scaler.scale_[feature_index]
                ),
                "semantic_group": group_name,
            }
        neurons.append(
            {
                "id": group_name,
                "display_name": display.get(group_name, group_name),
                "expected_direction": direction.get(
                    group_name, "unconstrained_v1"
                ),
                "feature_weights": feature_weights,
                "threshold": float(
                    model["thresholds"][index] - float(ridge.intercept_)
                ),
                "scale": float(model["scales"][index]),
                "neutral_activation": 0.5,
                "output_weight": float(output_weights[index]),
            }
        )
    config = {
        "model_id": "gl02_semantic_si_engine",
        "model_version": model_version,
        "model_status": "calibrated_experimental",
        "unit": "%",
        "distribution_family": "normal",
        "intercept": engine_intercept,
        "residual_std": float(residual_std),
        "target_band": {"low": TARGET_LOW, "high": TARGET_HIGH},
        "calibration_notice": (
            "V1代理时间对齐实验配置；只允许离线研究，不允许接生产MCP或操作建议。"
        ),
        "neurons": neurons,
    }
    contract = {
        "model_version": model_version,
        "input_contract": "apply train-only imputation and standardization",
        "features": feature_contract,
    }
    return config, contract


def standardized_engine_features(
    contract: Mapping[str, Any], frame: pd.DataFrame
) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for _, source_row in frame.iterrows():
        output: dict[str, float] = {}
        for source_name, item in contract["features"].items():
            raw = pd.to_numeric(
                pd.Series([source_row.get(source_name)]), errors="coerce"
            ).iloc[0]
            if pd.isna(raw):
                raw = item["impute_median"]
            scale = item["train_scale_after_imputation"] or 1.0
            output[item["standardized_name"]] = float(
                (float(raw) - item["train_mean_after_imputation"]) / scale
            )
        rows.append(output)
    return rows


def _calibration_std(actual: np.ndarray, predicted: np.ndarray) -> float:
    residual = np.asarray(actual, dtype=float) - np.asarray(
        predicted, dtype=float
    )
    if len(residual) < 2:
        return 0.10
    return float(max(np.std(residual, ddof=1), 0.01))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _artifact_hashes(directory: Path, exclude: set[str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        if relative in exclude or "__pycache__" in relative:
            continue
        output[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return output


def run_experiment(
    dataset_path: Path,
    prepared_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    models_dir = output_dir / "models"
    models_dir.mkdir(exist_ok=True)
    frame = pd.read_csv(dataset_path, low_memory=False, encoding="utf-8-sig")
    frame["feature_end_ts"] = pd.to_datetime(
        frame["feature_end_ts"], errors="raise"
    )
    frame = frame.sort_values(
        ["experiment_row_index", "feature_end_ts"], kind="stable"
    ).reset_index(drop=True)
    train = frame[frame["experiment_split"] == "train"].copy()
    validation = frame[frame["experiment_split"] == "validation"].copy()
    test = frame[frame["experiment_split"] == "test"].copy()
    if min(len(train), len(validation), len(test)) == 0:
        raise ValueError("训练、验证、测试集合都必须非空")

    rule_candidates, full_candidates = _candidate_columns(frame)
    rule_columns = _usable_columns(train, rule_candidates)
    full_columns = _usable_columns(train, full_candidates)
    semantic_groups = semantic_feature_groups(rule_columns)
    if len(semantic_groups) < 4:
        raise ValueError("可用语义神经元少于4个")

    y_train = train[TARGET_COLUMN].to_numpy(dtype=float)
    y_validation = validation[TARGET_COLUMN].to_numpy(dtype=float)
    y_test = test[TARGET_COLUMN].to_numpy(dtype=float)
    train_median = float(np.median(y_train))

    model_predictions: dict[str, dict[str, np.ndarray]] = {}
    model_objects: dict[str, Any] = {}

    for name, source_column in (
        ("previous_heat", "history__previous_Si_1"),
        ("recent3_median", "history__previous_Si_median_3"),
    ):
        model_predictions[name] = {}
        for split_name, split_frame in (
            ("validation", validation),
            ("test", test),
        ):
            values = pd.to_numeric(
                split_frame[source_column], errors="coerce"
            ).fillna(train_median)
            model_predictions[name][split_name] = values.to_numpy(dtype=float)

    rule_ridge = _ridge_pipeline(len(train))
    rule_ridge.fit(_numeric_frame(train, rule_columns), y_train)
    model_objects["rule_ridge"] = rule_ridge
    model_predictions["rule_ridge"] = {
        "validation": rule_ridge.predict(
            _numeric_frame(validation, rule_columns)
        ),
        "test": rule_ridge.predict(_numeric_frame(test, rule_columns)),
    }

    rule_hist = _hist_gradient_pipeline()
    rule_hist.fit(_numeric_frame(train, rule_columns), y_train)
    model_objects["rule_hist_gradient"] = rule_hist
    model_predictions["rule_hist_gradient"] = {
        "validation": rule_hist.predict(
            _numeric_frame(validation, rule_columns)
        ),
        "test": rule_hist.predict(_numeric_frame(test, rule_columns)),
    }

    full_trees = _extra_trees_pipeline()
    full_trees.fit(_numeric_frame(train, full_columns), y_train)
    model_objects["full_extra_trees"] = full_trees
    model_predictions["full_extra_trees"] = {
        "validation": full_trees.predict(
            _numeric_frame(validation, full_columns)
        ),
        "test": full_trees.predict(_numeric_frame(test, full_columns)),
    }

    semantic = fit_semantic_model(train, y_train, semantic_groups)
    model_objects["semantic_neurons"] = semantic
    model_predictions["semantic_neurons"] = {
        "validation": predict_semantic(semantic, validation),
        "test": predict_semantic(semantic, test),
    }

    metrics: dict[str, Any] = {}
    residual_stds: dict[str, float] = {}
    for name, predictions in model_predictions.items():
        residual_std = _calibration_std(
            y_validation, predictions["validation"]
        )
        residual_stds[name] = residual_std
        metrics[name] = {
            "validation": regression_metrics(
                y_validation,
                predictions["validation"],
                residual_std=residual_std,
            ),
            "test": regression_metrics(
                y_test,
                predictions["test"],
                residual_std=residual_std,
            ),
        }
    selected_model = min(
        metrics,
        key=lambda name: metrics[name]["validation"]["mae"],
    )
    experiment_id = output_dir.name
    semantic_config, feature_contract = export_semantic_engine(
        semantic,
        residual_stds["semantic_neurons"],
        model_version=experiment_id,
    )
    engine = SemanticSiEngine.from_mapping(semantic_config)
    check_rows = min(20, len(test))
    standardized = standardized_engine_features(
        feature_contract, test.iloc[:check_rows]
    )
    engine_prediction = np.asarray(
        [
            engine.predict(item)["distribution"]["mean"]
            for item in standardized
        ],
        dtype=float,
    )
    direct_prediction = model_predictions["semantic_neurons"]["test"][
        :check_rows
    ]
    engine_compatibility_max_abs = float(
        np.max(np.abs(engine_prediction - direct_prediction))
    )
    if engine_compatibility_max_abs > 1e-10:
        raise ValueError(
            "导出的语义引擎配置与训练管线预测不一致："
            f"{engine_compatibility_max_abs}"
        )

    validation_output = validation[
        [
            "temporary_heat_group",
            "feature_end_ts",
            TARGET_COLUMN,
            "target__Si_min",
            "target__Si_max",
            "target__Si_sample_count",
        ]
    ].copy()
    test_output = test[
        [
            "temporary_heat_group",
            "feature_end_ts",
            TARGET_COLUMN,
            "target__Si_min",
            "target__Si_max",
            "target__Si_sample_count",
        ]
    ].copy()
    for name, predictions in model_predictions.items():
        validation_output[f"prediction__{name}"] = predictions["validation"]
        test_output[f"prediction__{name}"] = predictions["test"]
        test_output[f"p10__{name}"] = (
            predictions["test"] - Z80 * residual_stds[name]
        )
        test_output[f"p90__{name}"] = (
            predictions["test"] + Z80 * residual_stds[name]
        )
    validation_output.to_csv(
        output_dir / "predictions_validation.csv",
        index=False,
        encoding="utf-8-sig",
    )
    test_output.to_csv(
        output_dir / "predictions_test.csv",
        index=False,
        encoding="utf-8-sig",
    )

    for name, model in model_objects.items():
        joblib.dump(
            model,
            models_dir / f"{name}.joblib",
            compress=3,
        )
    _write_json(output_dir / "metrics.json", metrics)
    _write_json(
        output_dir / "semantic_model_config.json", semantic_config
    )
    _write_json(output_dir / "feature_contract.json", feature_contract)
    feature_selection = {
        "rule_feature_count": len(rule_columns),
        "full_feature_count": len(full_columns),
        "semantic_groups": semantic_groups,
        "rule_features": rule_columns,
        "full_features": full_columns,
    }
    _write_json(output_dir / "feature_selection.json", feature_selection)
    tree_importance = sorted(
        (
            {
                "feature": feature,
                "importance": float(importance),
            }
            for feature, importance in zip(
                full_columns,
                full_trees.named_steps["model"].feature_importances_,
                strict=True,
            )
        ),
        key=lambda item: item["importance"],
        reverse=True,
    )
    ridge_importance = sorted(
        (
            {
                "feature": feature,
                "standardized_coefficient": float(coefficient),
                "absolute_standardized_coefficient": float(abs(coefficient)),
            }
            for feature, coefficient in zip(
                rule_columns,
                np.asarray(
                    rule_ridge.named_steps["model"].coef_,
                    dtype=float,
                ),
                strict=True,
            )
        ),
        key=lambda item: item["absolute_standardized_coefficient"],
        reverse=True,
    )
    importance_report = {
        "warning": (
            "Feature importance and coefficients describe association in the "
            "V1 proxy experiment; they are not causal adjustment effects."
        ),
        "full_extra_trees_top_50": tree_importance[:50],
        "rule_ridge_top_50": ridge_importance[:50],
        "semantic_output_weights": [
            {
                "neuron": neuron["id"],
                "display_name": neuron["display_name"],
                "output_weight": neuron["output_weight"],
                "expected_direction": neuron["expected_direction"],
            }
            for neuron in semantic_config["neurons"]
        ],
    }
    _write_json(
        output_dir / "feature_importance.json", importance_report
    )
    experiment_config = {
        "requirement_id": "REQ-SI-EXPERIMENT-V1-20260726",
        "experiment_id": experiment_id,
        "random_state": RANDOM_STATE,
        "dataset": {
            "path": str(dataset_path.resolve()),
            "sha256": sha256_file(dataset_path),
        },
        "prepared_manifest": {
            "path": str(prepared_manifest_path.resolve()),
            "sha256": sha256_file(prepared_manifest_path),
        },
        "split_rows": {
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
        "model_selection_metric": "validation_mae",
        "selected_model": selected_model,
        "semantic_engine_compatibility_max_abs": engine_compatibility_max_abs,
        "limitations": [
            "temporary heat group is derived from sample number",
            "feature cutoff uses result timestamp minus 120 minutes",
            "no exact burden chemistry lineage",
            "no complete 30/60/120/240 minute sensor window statistics",
            "experimental model must not be used for production control",
        ],
    }
    _write_json(output_dir / "experiment_config.json", experiment_config)

    report_lines = [
        f"# {experiment_id} 首轮训练报告",
        "",
        "## 结论",
        "",
        f"- 选择模型：`{selected_model}`（按验证集MAE）",
        f"- 训练/验证/测试炉次：{len(train)}/{len(validation)}/{len(test)}",
        f"- 规则特征：{len(rule_columns)}；全量特征：{len(full_columns)}",
        f"- 语义神经元：{len(semantic_groups)}",
        (
            "- 语义配置与训练管线最大预测差："
            f"`{engine_compatibility_max_abs:.3e}`"
        ),
        "",
        "## 指标",
        "",
        "| 模型 | 验证MAE | 测试MAE | 测试RMSE | ±0.05命中 | ±0.10命中 | 目标带分类 | P10-P90覆盖 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in metrics:
        validation_metric = metrics[name]["validation"]
        test_metric = metrics[name]["test"]
        report_lines.append(
            "| {name} | {vmae:.4f} | {tmae:.4f} | {trmse:.4f} | "
            "{hit05:.1%} | {hit10:.1%} | {band:.1%} | {coverage:.1%} |".format(
                name=name,
                vmae=validation_metric["mae"],
                tmae=test_metric["mae"],
                trmse=test_metric["rmse"],
                hit05=test_metric["hit_rate_abs_le_005"],
                hit10=test_metric["hit_rate_abs_le_010"],
                band=test_metric["target_band_class_accuracy"],
                coverage=test_metric["p10_p90_coverage"],
            )
        )
    report_lines.extend(
        [
            "",
            "## 预测范围与异常识别",
            "",
            (
                f"- 测试集真实Si中位数范围："
                f"`{float(np.min(y_test)):.3f}%～{float(np.max(y_test)):.3f}%`"
            ),
            (
                f"- 选中模型预测范围："
                f"`{float(np.min(model_predictions[selected_model]['test'])):.3f}%～"
                f"{float(np.max(model_predictions[selected_model]['test'])):.3f}%`"
            ),
            (
                "- 低Si/高Si召回："
                f"`{metrics[selected_model]['test']['low_si_recall']}` / "
                f"`{metrics[selected_model]['test']['high_si_recall']}`"
            ),
            "- 若异常召回接近0，即使总体MAE较低，也不得进入异常预警或操作建议。",
            "",
            "## 选中模型前十关联特征",
            "",
            "| 特征 | ExtraTrees重要性 |",
            "|---|---:|",
        ]
    )
    for item in tree_importance[:10]:
        report_lines.append(
            f"| `{item['feature']}` | {item['importance']:.6f} |"
        )
    report_lines.extend(
        [
            "",
            "## 边界",
            "",
            "本报告是V1代理时间对齐探索实验，不是生产模型验收。测试集未参与模型选择，"
            "但正式影子运行仍需用meltno、真实开堵口/取样时间和完整窗口重建V2。",
        ]
    )
    (output_dir / "report.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )

    run_manifest = {
        "experiment_id": experiment_id,
        "generated_at": datetime.now().astimezone().isoformat(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "sklearn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "selected_model": selected_model,
        "artifacts": _artifact_hashes(
            output_dir, exclude={"run_manifest.json"}
        ),
    }
    _write_json(output_dir / "run_manifest.json", run_manifest)
    return {
        "experiment_id": experiment_id,
        "selected_model": selected_model,
        "split_rows": experiment_config["split_rows"],
        "metrics": metrics,
        "output_dir": str(output_dir.resolve()),
        "run_manifest_sha256": sha256_file(
            output_dir / "run_manifest.json"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="执行固定的V1铁水Si语义神经元探索实验。"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_experiment(
        args.dataset,
        args.prepared_manifest,
        args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
