"""Run the V2 proxy experiment with expanded process-semantic neurons.

V2 keeps the immutable V1 dataset/split, changes the primary acceptance
tolerance to ±0.05 percentage points, and replaces six broad neurons with
smaller process-semantic groups. Complete 30/60/120/240-minute raw sensor
features are intentionally not claimed until the minute history is available.

Requirement:
    REQ-SI-TEMPORAL-NEURONS-V2-20260726
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy.special import expit
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge

from .engine import SemanticSiEngine
from .expanded_neurons import (
    LEGACY_ABSOLUTE_ERROR_TOLERANCE,
    PRIMARY_ABSOLUTE_ERROR_TOLERANCE,
    expanded_neuron_display_name,
    expanded_semantic_feature_groups,
)
from .experiment_data import TARGET_COLUMN, sha256_file
from .train_v1 import (
    Z80,
    _calibration_std,
    _candidate_columns,
    _extra_trees_pipeline,
    _hist_gradient_pipeline,
    _numeric_frame,
    _ridge_pipeline,
    _safe_float,
    _usable_columns,
    fit_semantic_model,
    predict_semantic,
    regression_metrics,
    semantic_feature_groups,
    standardized_engine_features,
)


REQUIREMENT_ID = "REQ-SI-TEMPORAL-NEURONS-V2-20260726"
RANDOM_STATE = 20260726


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _artifact_hashes(directory: Path) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        if relative == "run_manifest.json" or "__pycache__" in relative:
            continue
        output[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return output


def _semantic_activations(
    model: Mapping[str, Any],
    frame: pd.DataFrame,
) -> np.ndarray:
    responses = []
    for group_name in model["group_names"]:
        responses.append(
            model["inner_models"][group_name].predict(
                _numeric_frame(frame, model["groups"][group_name])
            )
        )
    response_matrix = np.column_stack(responses)
    return expit(
        (response_matrix - model["thresholds"]) / model["scales"]
    )


def semantic_group_ablation(
    model: Mapping[str, Any],
    frame: pd.DataFrame,
    actual: np.ndarray,
) -> list[dict[str, Any]]:
    """Neutralize one neuron at a time and report metric changes."""

    activations = _semantic_activations(model, frame)
    baseline_prediction = model["outer_model"].predict(activations)
    baseline = regression_metrics(actual, baseline_prediction)
    output = []
    for index, group_name in enumerate(model["group_names"]):
        neutralized = activations.copy()
        neutralized[:, index] = 0.5
        metrics = regression_metrics(
            actual,
            model["outer_model"].predict(neutralized),
        )
        output.append(
            {
                "neuron": group_name,
                "display_name": expanded_neuron_display_name(group_name),
                "feature_count": len(model["groups"][group_name]),
                "output_weight": float(model["outer_model"].coef_[index]),
                "neutralized_mae": metrics["mae"],
                "mae_delta_when_neutralized": (
                    metrics["mae"] - baseline["mae"]
                ),
                "hit_005_delta_when_neutralized": (
                    metrics["hit_rate_abs_le_005"]
                    - baseline["hit_rate_abs_le_005"]
                ),
            }
        )
    return output


def export_expanded_semantic_engine(
    model: Mapping[str, Any],
    residual_std: float,
    model_version: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Export a SemanticSiEngine-compatible experimental V2 configuration."""

    outer = model["outer_model"]
    output_weights = np.asarray(outer.coef_, dtype=float)
    engine_intercept = float(outer.intercept_) + 0.5 * float(
        output_weights.sum()
    )
    neurons = []
    feature_contract: dict[str, Any] = {}
    for index, group_name in enumerate(model["group_names"]):
        pipeline = model["inner_models"][group_name]
        imputer: SimpleImputer = pipeline.named_steps["imputer"]
        scaler = pipeline.named_steps["scaler"]
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
                "display_name": expanded_neuron_display_name(group_name),
                "expected_direction": (
                    "unconstrained_v2_pending_expert_review"
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
        "model_id": "gl02_expanded_semantic_si_engine",
        "model_version": model_version,
        "model_status": "calibrated_experimental",
        "unit": "%",
        "distribution_family": "normal",
        "intercept": engine_intercept,
        "residual_std": float(residual_std),
        "target_band": {"low": 0.20, "high": 0.40},
        "primary_absolute_error_tolerance_percentage_points": (
            PRIMARY_ABSOLUTE_ERROR_TOLERANCE
        ),
        "calibration_notice": (
            "V2扩展语义神经元代理实验；只允许离线研究。完整130点多窗口"
            "时序尚未物化，不允许接生产MCP或操作建议。"
        ),
        "neurons": neurons,
    }
    contract = {
        "model_version": model_version,
        "input_contract": "apply train-only imputation and standardization",
        "features": feature_contract,
    }
    return config, contract


def _model_selection_key(
    name: str,
    metrics: Mapping[str, Any],
) -> tuple[float, float, str]:
    validation = metrics[name]["validation"]
    return (
        -float(validation["hit_rate_abs_le_005"]),
        float(validation["mae"]),
        name,
    )


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
    split_frames = {
        name: frame[frame["experiment_split"] == name].copy()
        for name in ("train", "validation", "test")
    }
    if any(item.empty for item in split_frames.values()):
        raise ValueError("训练、验证、测试集合都必须非空")
    train = split_frames["train"]
    validation = split_frames["validation"]
    test = split_frames["test"]

    rule_candidates, full_candidates = _candidate_columns(frame)
    rule_columns = _usable_columns(train, rule_candidates)
    full_columns = _usable_columns(train, full_candidates)
    broad_groups = semantic_feature_groups(rule_columns)
    expanded_groups = expanded_semantic_feature_groups(rule_columns)
    if len(expanded_groups) < 12:
        raise ValueError("扩展语义神经元少于12个")

    y = {
        name: split_frames[name][TARGET_COLUMN].to_numpy(dtype=float)
        for name in split_frames
    }
    train_median = float(np.median(y["train"]))
    predictions: dict[str, dict[str, np.ndarray]] = {}
    models: dict[str, Any] = {}

    for name, source_column in (
        ("previous_heat", "history__previous_Si_1"),
        ("recent3_median", "history__previous_Si_median_3"),
    ):
        predictions[name] = {}
        for split_name in ("validation", "test"):
            values = pd.to_numeric(
                split_frames[split_name][source_column], errors="coerce"
            ).fillna(train_median)
            predictions[name][split_name] = values.to_numpy(dtype=float)

    rule_ridge = _ridge_pipeline(len(train))
    rule_ridge.fit(_numeric_frame(train, rule_columns), y["train"])
    models["rule_ridge"] = rule_ridge
    predictions["rule_ridge"] = {
        split: rule_ridge.predict(
            _numeric_frame(split_frames[split], rule_columns)
        )
        for split in ("validation", "test")
    }

    rule_hist = _hist_gradient_pipeline()
    rule_hist.fit(_numeric_frame(train, rule_columns), y["train"])
    models["rule_hist_gradient"] = rule_hist
    predictions["rule_hist_gradient"] = {
        split: rule_hist.predict(
            _numeric_frame(split_frames[split], rule_columns)
        )
        for split in ("validation", "test")
    }

    full_trees = _extra_trees_pipeline()
    full_trees.fit(_numeric_frame(train, full_columns), y["train"])
    models["full_extra_trees"] = full_trees
    predictions["full_extra_trees"] = {
        split: full_trees.predict(
            _numeric_frame(split_frames[split], full_columns)
        )
        for split in ("validation", "test")
    }

    broad_semantic = fit_semantic_model(
        train, y["train"], broad_groups
    )
    models["semantic_neurons_6"] = broad_semantic
    predictions["semantic_neurons_6"] = {
        split: predict_semantic(broad_semantic, split_frames[split])
        for split in ("validation", "test")
    }

    expanded_semantic = fit_semantic_model(
        train, y["train"], expanded_groups
    )
    models["semantic_neurons_expanded"] = expanded_semantic
    predictions["semantic_neurons_expanded"] = {
        split: predict_semantic(expanded_semantic, split_frames[split])
        for split in ("validation", "test")
    }

    metrics: dict[str, Any] = {}
    residual_stds: dict[str, float] = {}
    for name, split_predictions in predictions.items():
        residual_std = _calibration_std(
            y["validation"], split_predictions["validation"]
        )
        residual_stds[name] = residual_std
        metrics[name] = {
            split: regression_metrics(
                y[split],
                split_predictions[split],
                residual_std=residual_std,
            )
            for split in ("validation", "test")
        }
    selected_model = min(
        metrics,
        key=lambda name: _model_selection_key(name, metrics),
    )

    experiment_id = output_dir.name
    semantic_config, feature_contract = export_expanded_semantic_engine(
        expanded_semantic,
        residual_stds["semantic_neurons_expanded"],
        experiment_id,
    )
    engine = SemanticSiEngine.from_mapping(semantic_config)
    check_count = min(20, len(test))
    standardized = standardized_engine_features(
        feature_contract, test.iloc[:check_count]
    )
    engine_prediction = np.asarray(
        [
            engine.predict(item)["distribution"]["mean"]
            for item in standardized
        ]
    )
    direct_prediction = predictions["semantic_neurons_expanded"]["test"][
        :check_count
    ]
    compatibility = float(
        np.max(np.abs(engine_prediction - direct_prediction))
    )
    if compatibility > 1e-10:
        raise ValueError(
            f"导出配置与扩展神经元预测不一致：{compatibility}"
        )

    ablation = {
        split: semantic_group_ablation(
            expanded_semantic,
            split_frames[split],
            y[split],
        )
        for split in ("validation", "test")
    }
    _write_json(output_dir / "ablation.json", ablation)
    _write_json(output_dir / "metrics.json", metrics)
    _write_json(
        output_dir / "semantic_model_config.json", semantic_config
    )
    _write_json(output_dir / "feature_contract.json", feature_contract)
    _write_json(
        output_dir / "feature_selection.json",
        {
            "rule_feature_count": len(rule_columns),
            "full_feature_count": len(full_columns),
            "broad_semantic_groups": broad_groups,
            "expanded_semantic_groups": expanded_groups,
            "expanded_semantic_group_count": len(expanded_groups),
            "expanded_assigned_feature_count": sum(
                len(values) for values in expanded_groups.values()
            ),
            "unassigned_rule_features": sorted(
                set(rule_columns).difference(
                    item
                    for values in expanded_groups.values()
                    for item in values
                )
            ),
        },
    )

    for name, model in models.items():
        joblib.dump(
            model,
            models_dir / f"{name}.joblib",
            compress=3,
        )

    for split in ("validation", "test"):
        columns = [
            "temporary_heat_group",
            "feature_end_ts",
            TARGET_COLUMN,
            "target__Si_min",
            "target__Si_max",
            "target__Si_sample_count",
        ]
        output = split_frames[split][columns].copy()
        for name, split_predictions in predictions.items():
            output[f"prediction__{name}"] = split_predictions[split]
            if split == "test":
                output[f"p10__{name}"] = (
                    split_predictions[split] - Z80 * residual_stds[name]
                )
                output[f"p90__{name}"] = (
                    split_predictions[split] + Z80 * residual_stds[name]
                )
        output.to_csv(
            output_dir / f"predictions_{split}.csv",
            index=False,
            encoding="utf-8-sig",
        )

    tree_importance = sorted(
        (
            {"feature": feature, "importance": float(importance)}
            for feature, importance in zip(
                full_columns,
                full_trees.named_steps["model"].feature_importances_,
                strict=True,
            )
        ),
        key=lambda item: item["importance"],
        reverse=True,
    )
    _write_json(
        output_dir / "feature_importance.json",
        {
            "warning": (
                "Associations in a V1 proxy-alignment dataset are not causal "
                "adjustment effects."
            ),
            "full_extra_trees_top_50": tree_importance[:50],
            "expanded_semantic_output_weights": [
                {
                    "neuron": neuron["id"],
                    "display_name": neuron["display_name"],
                    "output_weight": neuron["output_weight"],
                }
                for neuron in semantic_config["neurons"]
            ],
        },
    )

    experiment_config = {
        "requirement_id": REQUIREMENT_ID,
        "experiment_id": experiment_id,
        "random_state": RANDOM_STATE,
        "primary_acceptance": {
            "metric": "absolute_error_hit_rate",
            "tolerance_percentage_points": (
                PRIMARY_ABSOLUTE_ERROR_TOLERANCE
            ),
            "model_selection": (
                "maximize validation hit_rate_abs_le_005, then minimize "
                "validation MAE"
            ),
        },
        "legacy_tolerance": {
            "tolerance_percentage_points": (
                LEGACY_ABSOLUTE_ERROR_TOLERANCE
            ),
            "status": "diagnostic_only",
        },
        "dataset": {
            "path": str(dataset_path.resolve()),
            "sha256": sha256_file(dataset_path),
            "complete_raw_temporal_windows_materialized": False,
        },
        "prepared_manifest": {
            "path": str(prepared_manifest_path.resolve()),
            "sha256": sha256_file(prepared_manifest_path),
        },
        "split_rows": {
            name: len(split_frames[name]) for name in split_frames
        },
        "selected_model": selected_model,
        "expanded_semantic_group_count": len(expanded_groups),
        "semantic_engine_compatibility_max_abs": compatibility,
        "limitations": [
            "temporary heat group is derived from sample number",
            "feature cutoff uses result timestamp minus 120 minutes",
            "local PostgreSQL has no bf_sensor schema",
            "complete 30/60/120/240-minute 130-point features are not materialized",
            "experimental model must not be used for production control",
        ],
    }
    _write_json(output_dir / "experiment_config.json", experiment_config)

    lines = [
        f"# {experiment_id} 扩展语义神经元实验",
        "",
        "## 结论",
        "",
        f"- 主验收容差：`±{PRIMARY_ABSOLUTE_ERROR_TOLERANCE:.2f}` 个Si百分点。",
        "- `±0.10`仅保留为历史诊断指标，不再作为主验收。",
        f"- 扩展语义神经元：{len(expanded_groups)}个（原模型6个）。",
        f"- 选择模型：`{selected_model}`。",
        "- 当前仍使用V1代理快照，130点完整多窗口特征尚未物化。",
        "",
        "## 指标",
        "",
        "| 模型 | 验证±0.05 | 测试±0.05 | 验证MAE | 测试MAE | 测试R² |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, value in metrics.items():
        validation_metric = value["validation"]
        test_metric = value["test"]
        lines.append(
            "| {name} | {vhit:.1%} | {thit:.1%} | {vmae:.4f} | "
            "{tmae:.4f} | {r2:.4f} |".format(
                name=name,
                vhit=validation_metric["hit_rate_abs_le_005"],
                thit=test_metric["hit_rate_abs_le_005"],
                vmae=validation_metric["mae"],
                tmae=test_metric["mae"],
                r2=test_metric["r2"],
            )
        )
    lines.extend(
        [
            "",
            "## 扩展神经元",
            "",
            "| 神经元 | 特征数 | 验证集去除后的MAE变化 | 测试集去除后的MAE变化 |",
            "|---|---:|---:|---:|",
        ]
    )
    validation_ablation = {
        item["neuron"]: item for item in ablation["validation"]
    }
    test_ablation = {item["neuron"]: item for item in ablation["test"]}
    for group_name in expanded_groups:
        validation_item = validation_ablation[group_name]
        test_item = test_ablation[group_name]
        lines.append(
            "| {display} | {count} | {vdelta:+.6f} | {tdelta:+.6f} |".format(
                display=expanded_neuron_display_name(group_name),
                count=len(expanded_groups[group_name]),
                vdelta=validation_item["mae_delta_when_neutralized"],
                tdelta=test_item["mae_delta_when_neutralized"],
            )
        )
    lines.extend(
        [
            "",
            "正值表示去除后MAE变差，即该神经元在该时间段有帮助；负值表示不稳定或拖累。",
            "",
            "## 边界",
            "",
            "本实验只验证扩展分组方法，不能替代真实130点多窗口训练。只有本机完成",
            "`bf_sensor.one_minute_values`受控同步、正式炉次时间对齐和滚动月份回测后，",
            "才能判断新增时序神经元是否稳定有效。",
        ]
    )
    (output_dir / "report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
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
        "artifacts": _artifact_hashes(output_dir),
    }
    _write_json(output_dir / "run_manifest.json", run_manifest)
    return {
        "experiment_id": experiment_id,
        "selected_model": selected_model,
        "expanded_semantic_group_count": len(expanded_groups),
        "metrics": metrics,
        "output_dir": str(output_dir.resolve()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行±0.05主验收和扩展语义神经元V2代理实验。"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_experiment(
        args.dataset,
        args.prepared_manifest,
        args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
