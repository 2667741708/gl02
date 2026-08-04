"""Iterate leakage-safe semantic/physical Si models against a locked test set.

The V3 dataset is read-only.  Candidate feature blocks and model parameters
are selected exclusively by the chronological validation segment.  The test
segment is evaluated once after selection.

Requirement:
    REQ-SI-SEMANTIC-HYBRID-V4-20260726
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline

from .formal_dataset import sha256_file
from .train_v3 import TARGET, _candidate_features, _usable_features
from .v4_features import build_v4_feature_blocks


REQUIREMENT_ID = "REQ-SI-SEMANTIC-HYBRID-V4-20260726"
RANDOM_STATE = 20260726


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
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


def _numeric(frame: pd.DataFrame, features: Sequence[str]) -> pd.DataFrame:
    return frame[list(features)].apply(pd.to_numeric, errors="coerce")


def _pipeline(model: Any) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("model", model),
        ]
    )


def _model_candidates() -> dict[str, Pipeline]:
    return {
        "extra_trees_leaf2_f050": _pipeline(
            ExtraTreesRegressor(
                n_estimators=450,
                min_samples_leaf=2,
                max_features=0.50,
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )
        ),
        "extra_trees_leaf3_f070": _pipeline(
            ExtraTreesRegressor(
                n_estimators=450,
                min_samples_leaf=3,
                max_features=0.70,
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )
        ),
        "extra_trees_leaf5_f070": _pipeline(
            ExtraTreesRegressor(
                n_estimators=450,
                min_samples_leaf=5,
                max_features=0.70,
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )
        ),
        "extra_trees_leaf8_f100": _pipeline(
            ExtraTreesRegressor(
                n_estimators=450,
                min_samples_leaf=8,
                max_features=1.0,
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )
        ),
        "random_forest_leaf5_f050": _pipeline(
            RandomForestRegressor(
                n_estimators=450,
                min_samples_leaf=5,
                max_features=0.50,
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )
        ),
    }


def _usable_block(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    columns: Sequence[str],
) -> tuple[list[str], dict[str, Any]]:
    return _usable_features(
        combined.loc[train_mask],
        list(columns),
        min_non_null_ratio=0.50,
    )


def _feature_sets(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    block_columns: dict[str, list[str]],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    base_candidates = _candidate_features(combined)
    base_features, base_audit = _usable_block(
        combined, train_mask, base_candidates
    )
    additions = {
        "history": block_columns["history_v4"],
        "physics": (
            block_columns["physics"] + block_columns["interactions"]
        ),
    }
    history_features, history_audit = _usable_block(
        combined, train_mask, additions["history"]
    )
    physics_features, physics_audit = _usable_block(
        combined, train_mask, additions["physics"]
    )
    semantic_candidates = (
        block_columns["semantic"]
        + history_features
        + physics_features
    )
    semantic_features, semantic_audit = _usable_block(
        combined, train_mask, semantic_candidates
    )
    feature_sets = {
        "v3_base": base_features,
        "v3_plus_history": sorted(set(base_features + history_features)),
        "v3_plus_physics": sorted(set(base_features + physics_features)),
        "v4_all": sorted(
            set(base_features + history_features + physics_features)
        ),
        "v4_semantic_named": semantic_features,
    }
    return feature_sets, {
        "v3_base": base_audit,
        "history_v4": history_audit,
        "physics_and_interactions": physics_audit,
        "v4_semantic_named": semantic_audit,
        "feature_set_counts": {
            name: len(features) for name, features in feature_sets.items()
        },
    }


def _selection_key(metrics: dict[str, float], name: str) -> tuple[Any, ...]:
    return (
        metrics["mae"],
        -metrics["hit_rate_abs_le_002"],
        metrics["rmse"],
        name,
    )


def _previous_si_prediction(
    frame: pd.DataFrame,
    train_median: float,
) -> np.ndarray:
    source = pd.to_numeric(
        frame["history_v4__Si_w6__median"], errors="coerce"
    ).fillna(train_median)
    return source.to_numpy(float)


def _select_history_blend(
    actual: np.ndarray,
    model_prediction: np.ndarray,
    history_prediction: np.ndarray,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for model_weight in np.linspace(0.0, 1.0, 21):
        prediction = (
            model_weight * model_prediction
            + (1.0 - model_weight) * history_prediction
        )
        metrics = _metrics(actual, prediction)
        candidates.append(
            {
                "model_weight": float(model_weight),
                "history_weight": float(1.0 - model_weight),
                "metrics": metrics,
            }
        )
    return min(
        candidates,
        key=lambda item: _selection_key(
            item["metrics"], f"{item['model_weight']:.2f}"
        ),
    )


def _monthly_metrics(
    frame: pd.DataFrame,
    prediction: np.ndarray,
) -> dict[str, Any]:
    working = frame[["prediction_cutoff_ts", TARGET]].copy()
    working["prediction"] = prediction
    working["month"] = working["prediction_cutoff_ts"].dt.strftime("%Y-%m")
    output: dict[str, Any] = {}
    for month, part in working.groupby("month", sort=True):
        output[str(month)] = _metrics(
            part[TARGET].to_numpy(float),
            part["prediction"].to_numpy(float),
        )
    return output


def _artifact_hashes(directory: Path) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        if path.name in {"run_manifest.json", "sha256sums.json"}:
            continue
        relative = path.relative_to(directory).as_posix()
        output[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return output


def run_experiment(
    *,
    dataset_path: Path,
    heat_targets_path: Path,
    catalog_path: Path,
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
    frame["prediction_cutoff_ts"] = pd.to_datetime(
        frame["prediction_cutoff_ts"], errors="raise"
    )
    frame = frame.sort_values(
        ["experiment_row_index", "prediction_cutoff_ts"], kind="stable"
    ).reset_index(drop=True)
    if frame["official_meltno"].duplicated().any():
        raise RuntimeError("同一正式meltno跨行出现")

    blocks, feature_derivation_audit = build_v4_feature_blocks(
        frame, heat_targets, catalog_path
    )
    combined = pd.concat([frame, *blocks.values()], axis=1)
    split_masks = {
        name: combined["experiment_split"].eq(name)
        for name in ("train", "validation", "test")
    }
    if any(not bool(mask.any()) for mask in split_masks.values()):
        raise RuntimeError("训练、验证或测试时间段为空")
    feature_sets, feature_selection_audit = _feature_sets(
        combined,
        split_masks["train"],
        {name: list(block.columns) for name, block in blocks.items()},
    )
    train = combined.loc[split_masks["train"]].copy()
    validation = combined.loc[split_masks["validation"]].copy()
    test = combined.loc[split_masks["test"]].copy()

    validation_results: dict[str, Any] = {}
    fitted: dict[str, tuple[Pipeline, list[str], np.ndarray]] = {}
    for feature_set_name, features in feature_sets.items():
        for model_name, model in _model_candidates().items():
            candidate_name = f"{feature_set_name}__{model_name}"
            model.fit(_numeric(train, features), train[TARGET].to_numpy(float))
            prediction = model.predict(_numeric(validation, features))
            metrics = _metrics(
                validation[TARGET].to_numpy(float), prediction
            )
            validation_results[candidate_name] = {
                "feature_set": feature_set_name,
                "model": model_name,
                "feature_count": len(features),
                "metrics": metrics,
            }
            fitted[candidate_name] = (model, features, prediction)

    selected_name = min(
        validation_results,
        key=lambda name: _selection_key(
            validation_results[name]["metrics"], name
        ),
    )
    selected_model, selected_features, validation_prediction = fitted[
        selected_name
    ]
    train_median = float(train[TARGET].median())
    validation_history = _previous_si_prediction(validation, train_median)
    blend = _select_history_blend(
        validation[TARGET].to_numpy(float),
        validation_prediction,
        validation_history,
    )
    test_model_prediction = selected_model.predict(
        _numeric(test, selected_features)
    )
    test_history = _previous_si_prediction(test, train_median)
    selected_weight = float(blend["model_weight"])
    test_blended_prediction = (
        selected_weight * test_model_prediction
        + (1.0 - selected_weight) * test_history
    )
    raw_test_metrics = _metrics(
        test[TARGET].to_numpy(float), test_model_prediction
    )
    blended_test_metrics = _metrics(
        test[TARGET].to_numpy(float), test_blended_prediction
    )
    validation_blended_prediction = (
        selected_weight * validation_prediction
        + (1.0 - selected_weight) * validation_history
    )

    joblib.dump(
        {
            "model": selected_model,
            "features": selected_features,
            "selected_candidate": selected_name,
            "history_blend": {
                "model_weight": selected_weight,
                "history_weight": 1.0 - selected_weight,
                "history_feature": "history_v4__Si_w6__median",
                "fallback_train_median": train_median,
            },
            "model_status": "experimental_offline_v4",
        },
        models_dir / "selected_v4.joblib",
    )
    importance_model = selected_model.named_steps["model"]
    importances = getattr(importance_model, "feature_importances_", None)
    feature_importance = (
        sorted(
            (
                {"feature": feature, "importance": float(importance)}
                for feature, importance in zip(
                    selected_features, importances
                )
            ),
            key=lambda item: item["importance"],
            reverse=True,
        )
        if importances is not None
        else []
    )

    predictions = test[
        [
            "official_meltno",
            "prediction_cutoff_ts",
            TARGET,
            "target__Si_sample_count",
        ]
    ].copy()
    predictions["prediction__model"] = test_model_prediction
    predictions["prediction__history_w6"] = test_history
    predictions["prediction__selected_blend"] = test_blended_prediction
    predictions["absolute_error"] = np.abs(
        predictions[TARGET] - predictions["prediction__selected_blend"]
    )
    predictions.to_csv(
        output_dir / "predictions_test.csv",
        index=False,
        encoding="utf-8-sig",
    )

    metrics = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v4",
        "selection_contract": (
            "feature set, model and blend weight selected on validation only; "
            "locked test evaluated after selection"
        ),
        "baseline_v3_locked_test": {
            "mae": 0.04885118604651157,
            "hit_rate_abs_le_002": 0.30523255813953487,
            "hit_rate_abs_le_005": 0.6453488372093024,
        },
        "validation_candidates": validation_results,
        "selected": {
            **validation_results[selected_name],
            "candidate": selected_name,
            "history_blend_validation": blend,
            "validation_blended_metrics": _metrics(
                validation[TARGET].to_numpy(float),
                validation_blended_prediction,
            ),
            "test_raw_model_metrics": raw_test_metrics,
            "test_blended_metrics": blended_test_metrics,
            "test_monthly_metrics": _monthly_metrics(
                test, test_blended_prediction
            ),
        },
    }
    _write_json(output_dir / "metrics.json", metrics)
    _write_json(
        output_dir / "feature_derivation_audit.json",
        feature_derivation_audit,
    )
    _write_json(
        output_dir / "feature_selection_audit.json",
        feature_selection_audit,
    )
    _write_json(output_dir / "feature_importance.json", feature_importance[:200])
    _write_json(
        output_dir / "model_config.json",
        {
            "model_id": "gl02_formal_meltno_si_v4_semantic_hybrid",
            "model_version": output_dir.name,
            "model_status": "experimental_offline_v4",
            "online_allowed": False,
            "selected_candidate": selected_name,
            "selected_feature_count": len(selected_features),
            "history_blend": {
                "model_weight": selected_weight,
                "history_weight": 1.0 - selected_weight,
            },
            "target_goal": {
                "mae": 0.02,
                "tolerance": 0.02,
                "status": (
                    "reached"
                    if blended_test_metrics["mae"] <= 0.02
                    else "not_reached"
                ),
            },
        },
    )
    report = [
        "# V4 语义/物理神经元迭代报告",
        "",
        f"- 实验状态：`experimental_offline_v4`",
        f"- 选中候选：`{selected_name}`",
        f"- 选中特征数：{len(selected_features)}",
        f"- 验证MAE：{validation_results[selected_name]['metrics']['mae']:.6f}% Si",
        (
            "- 验证±0.02命中率："
            f"{validation_results[selected_name]['metrics']['hit_rate_abs_le_002']:.2%}"
        ),
        f"- 历史混合模型权重：{selected_weight:.2f}",
        f"- 测试MAE：{blended_test_metrics['mae']:.6f}% Si",
        (
            "- 测试±0.02命中率："
            f"{blended_test_metrics['hit_rate_abs_le_002']:.2%}"
        ),
        (
            "- 测试±0.05命中率："
            f"{blended_test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        "",
        "## 边界",
        "",
        "- V3原始数据未修改。",
        "- 历史Si只允许使用当前开铁截止前已经发布的更早炉次。",
        "- 物理动态由当前快照和已记录60/120分钟变化量重建。",
        "- 候选选择不读取测试指标；当前仍禁止接入生产MCP。",
        "",
    ]
    (output_dir / "report.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    manifest = {
        "requirement_id": REQUIREMENT_ID,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": {
            "dataset": {
                "path": str(dataset_path.resolve()),
                "sha256": sha256_file(dataset_path),
            },
            "heat_targets": {
                "path": str(heat_targets_path.resolve()),
                "sha256": sha256_file(heat_targets_path),
            },
            "sensor_catalog": {
                "path": str(catalog_path.resolve()),
                "sha256": sha256_file(catalog_path),
            },
        },
        "runtime": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "random_state": RANDOM_STATE,
        },
        "split_counts": {
            name: int(mask.sum()) for name, mask in split_masks.items()
        },
        "selected_candidate": selected_name,
        "selected_feature_count": len(selected_features),
        "artifacts": _artifact_hashes(output_dir),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_json(output_dir / "sha256sums.json", _artifact_hashes(output_dir))
    return metrics


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="运行正式炉次Si V4语义/物理神经元离线迭代。"
    )
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--heat-targets", type=Path, required=True)
    cli.add_argument("--sensor-catalog", type=Path, required=True)
    cli.add_argument("--output-dir", type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    metrics = run_experiment(
        dataset_path=args.dataset,
        heat_targets_path=args.heat_targets,
        catalog_path=args.sensor_catalog,
        output_dir=args.output_dir,
    )
    print(json.dumps(metrics["selected"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
