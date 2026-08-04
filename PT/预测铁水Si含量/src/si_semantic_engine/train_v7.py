"""Train a leakage-safe three-component Si ensemble.

The ensemble combines:

1. a direct ExtraTrees sensor/history model;
2. the V6 heat-state + chemistry residual XGBoost model;
3. a previously published Si history baseline.

Non-negative weights are selected only from April/May expanding folds and the
fixed June validation segment.  The final model is then refit on all pre-July
rows before the historical July evaluation.

Requirement:
    REQ-SI-ROBUST-ENSEMBLE-V7-20260727
"""

from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost

from .formal_dataset import sha256_file
from .train_v3 import TARGET
from .train_v4 import _feature_sets
from .train_v6 import (
    ModelSpec,
    _artifact_hashes,
    _feature_recipes,
    _fit_candidate,
    _history_baseline,
    _predict_candidate,
    _temperature_label_audit,
    _write_json,
    metrics,
)
from .v4_features import build_v4_feature_blocks
from .v5_features import (
    derive_temporal_spatial_neurons,
    load_temporal_statistics,
    pivot_temporal_statistics,
)
from .v6_features import (
    attach_published_chemistry_history,
    derive_heat_state_neurons,
    derive_multiscale_neurons,
)


REQUIREMENT_ID = "REQ-SI-ROBUST-ENSEMBLE-V7-20260727"
DIRECT_SPEC = ModelSpec(
    name="direct_extra2",
    family="extra_leaf2_f050",
    target_mode="direct",
)
THERMAL_SPEC = ModelSpec(
    name="thermal_chem_xgb3_residual_decay90",
    family="xgb_depth3",
    target_mode="residual",
    recency_half_life_days=90.0,
)


def _component_predictions(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    evaluation_mask: pd.Series,
    *,
    base_history: Sequence[str],
    temporal_columns: Sequence[str],
    multiscale_columns: Sequence[str],
    heat_state_columns: Sequence[str],
    spatial_columns: Sequence[str],
    chemistry_columns: Sequence[str],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    recipes, selection_audit = _feature_recipes(
        combined,
        train_mask,
        base_history=base_history,
        temporal_columns=temporal_columns,
        multiscale_columns=multiscale_columns,
        heat_state_columns=heat_state_columns,
        spatial_columns=spatial_columns,
        chemistry_columns=chemistry_columns,
    )
    train = combined.loc[train_mask]
    evaluation = combined.loc[evaluation_mask]
    fallback = float(train[TARGET].median())
    direct_features = recipes["base_history"]
    thermal_features = recipes["base_chemistry_heat250"]
    direct_model, direct_prediction = _fit_candidate(
        DIRECT_SPEC,
        train,
        evaluation,
        direct_features,
        fallback=fallback,
    )
    thermal_model, thermal_prediction = _fit_candidate(
        THERMAL_SPEC,
        train,
        evaluation,
        thermal_features,
        fallback=fallback,
    )
    history_prediction = _history_baseline(
        evaluation, fallback=fallback
    ).to_numpy(float)
    return {
        "direct": direct_prediction,
        "thermal": thermal_prediction,
        "history": history_prediction,
    }, {
        "direct_model": direct_model,
        "thermal_model": thermal_model,
        "direct_features": direct_features,
        "thermal_features": thermal_features,
        "fallback": fallback,
        "feature_selection": selection_audit,
    }


def _weight_grid(step: float = 0.05) -> list[dict[str, float]]:
    units = int(round(1.0 / step))
    output: list[dict[str, float]] = []
    for direct in range(units + 1):
        for thermal in range(units - direct + 1):
            history = units - direct - thermal
            output.append(
                {
                    "direct": direct / units,
                    "thermal": thermal / units,
                    "history": history / units,
                }
            )
    return output


def _blend(
    components: dict[str, np.ndarray],
    weights: dict[str, float],
) -> np.ndarray:
    return sum(
        float(weights[name]) * np.asarray(components[name], dtype=float)
        for name in ("direct", "thermal", "history")
    )


def _select_weights(
    fold_predictions: dict[str, dict[str, Any]],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    for weights in _weight_grid():
        folds: dict[str, dict[str, float]] = {}
        for name, fold in fold_predictions.items():
            prediction = _blend(fold["components"], weights)
            folds[name] = metrics(fold["actual"], prediction)
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
                "weights": weights,
                "folds": folds,
                "mean_mae": float(np.mean(maes)),
                "std_mae": float(np.std(maes, ddof=0)),
                "max_fold_mae": float(np.max(maes)),
                "mean_hit_rate_abs_le_002": float(np.mean(hits)),
                "robust_mae_score": float(
                    np.mean(maes) + 0.50 * np.std(maes, ddof=0)
                ),
            }
        )
    ranking = sorted(
        candidates,
        key=lambda item: (
            item["robust_mae_score"],
            item["max_fold_mae"],
            -item["mean_hit_rate_abs_le_002"],
            item["weights"]["direct"],
            item["weights"]["thermal"],
        ),
    )
    return ranking[0]["weights"], ranking


def _assemble_features(
    *,
    dataset_path: Path,
    heat_targets_path: Path,
    samples_path: Path,
    catalog_path: Path,
    temporal_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
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
    chemistry, chemistry_audit = attach_published_chemistry_history(
        frame, samples
    )
    combined = pd.concat(
        [
            frame,
            *v4_blocks.values(),
            temporal,
            spatial,
            multiscale,
            heat_state,
            chemistry,
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan)
    initial_train_mask = combined["experiment_split"].eq("train")
    v4_feature_sets, _ = _feature_sets(
        combined,
        initial_train_mask,
        {name: list(block.columns) for name, block in v4_blocks.items()},
    )
    return combined, {
        "base_history": v4_feature_sets["v3_plus_history"],
        "temporal_columns": list(temporal.columns),
        "spatial_columns": list(spatial.columns),
        "multiscale_columns": list(multiscale.columns),
        "heat_state_columns": list(heat_state.columns),
        "chemistry_columns": list(chemistry.columns),
        "windows_minutes": list(windows),
        "v4_audit": v4_audit,
        "temporal_audit": temporal_audit,
        "chemistry_audit": chemistry_audit,
        "temporal_manifest": temporal_manifest,
        "heat_targets": heat_targets,
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
    combined, blocks = _assemble_features(
        dataset_path=dataset_path,
        heat_targets_path=heat_targets_path,
        samples_path=samples_path,
        catalog_path=catalog_path,
        temporal_dir=temporal_dir,
    )
    feature_args = {
        "base_history": blocks["base_history"],
        "temporal_columns": blocks["temporal_columns"],
        "multiscale_columns": blocks["multiscale_columns"],
        "heat_state_columns": blocks["heat_state_columns"],
        "spatial_columns": blocks["spatial_columns"],
        "chemistry_columns": blocks["chemistry_columns"],
    }

    folds: dict[str, tuple[pd.Series, pd.Series]] = {}
    for month in ("2026-04", "2026-05"):
        folds[month] = (
            combined["prediction_month"].lt(month),
            combined["prediction_month"].eq(month),
        )
    folds["2026-06_fixed_validation"] = (
        combined["experiment_split"].eq("train"),
        combined["experiment_split"].eq("validation"),
    )
    fold_predictions: dict[str, dict[str, Any]] = {}
    fold_audit: dict[str, Any] = {}
    for name, (train_mask, evaluation_mask) in folds.items():
        components, audit = _component_predictions(
            combined,
            train_mask,
            evaluation_mask,
            **feature_args,
        )
        fold_predictions[name] = {
            "components": components,
            "actual": combined.loc[
                evaluation_mask, TARGET
            ].to_numpy(float),
        }
        fold_audit[name] = {
            "train_rows": int(train_mask.sum()),
            "evaluation_rows": int(evaluation_mask.sum()),
            "train_end": str(
                combined.loc[train_mask, "prediction_cutoff_ts"].max()
            ),
            "evaluation_start": str(
                combined.loc[
                    evaluation_mask, "prediction_cutoff_ts"
                ].min()
            ),
            "direct_feature_count": len(audit["direct_features"]),
            "thermal_feature_count": len(audit["thermal_features"]),
        }
    weights, weight_ranking = _select_weights(fold_predictions)

    test_mask = combined["experiment_split"].eq("test")
    initial_train_mask = combined["experiment_split"].eq("train")
    pretest_mask = ~test_mask
    train_only_components, train_only_audit = _component_predictions(
        combined,
        initial_train_mask,
        test_mask,
        **feature_args,
    )
    refit_components, refit_audit = _component_predictions(
        combined,
        pretest_mask,
        test_mask,
        **feature_args,
    )
    test = combined.loc[test_mask].copy()
    actual = test[TARGET].to_numpy(float)
    train_only_prediction = _blend(train_only_components, weights)
    refit_prediction = _blend(refit_components, weights)
    train_only_metrics = metrics(actual, train_only_prediction)
    refit_metrics = metrics(actual, refit_prediction)
    component_metrics = {
        name: metrics(actual, prediction)
        for name, prediction in refit_components.items()
    }

    predictions = test[
        ["official_meltno", "prediction_cutoff_ts", TARGET]
    ].copy()
    for name, prediction in refit_components.items():
        predictions[f"prediction__component_{name}"] = prediction
    predictions["prediction__Si_train_only_ensemble"] = (
        train_only_prediction
    )
    predictions["prediction__Si_refit_ensemble"] = refit_prediction
    predictions["absolute_error"] = np.abs(
        predictions[TARGET] - refit_prediction
    )
    predictions.to_csv(
        output_dir / "predictions_test.csv",
        index=False,
        encoding="utf-8-sig",
    )
    joblib.dump(
        {
            "direct_model": refit_audit["direct_model"],
            "thermal_model": refit_audit["thermal_model"],
            "direct_features": refit_audit["direct_features"],
            "thermal_features": refit_audit["thermal_features"],
            "fallback": refit_audit["fallback"],
            "weights": weights,
            "direct_spec": DIRECT_SPEC,
            "thermal_spec": THERMAL_SPEC,
            "status": "experimental_offline_v7",
        },
        models_dir / "selected_v7_ensemble.joblib",
    )

    temperature_audit = _temperature_label_audit(
        combined, blocks["heat_targets"]
    )
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v7",
        "selection_contract": (
            "weights selected on April/May expanding folds plus fixed June "
            "validation; final components refit on all rows before July; "
            "historical July has been reused across versions"
        ),
        "selected_weights": weights,
        "pretest_fold_audit": fold_audit,
        "weight_ranking_top30": weight_ranking[:30],
        "historical_test": {
            "train_only_comparable": train_only_metrics,
            "refit_train_plus_validation": refit_metrics,
            "refit_components": component_metrics,
        },
        "joint_task_readiness": {
            "si_point_head": "trained_experimental_offline_v7",
            **temperature_audit,
        },
        "goal": {
            "mae_target": 0.02,
            "tolerance_target": 0.02,
            "status": (
                "reached" if refit_metrics["mae"] <= 0.02 else "not_reached"
            ),
        },
    }
    _write_json(output_dir / "metrics.json", result)
    _write_json(
        output_dir / "feature_contract.json",
        {
            "windows_minutes": blocks["windows_minutes"],
            "v4_derivation": blocks["v4_audit"],
            "temporal_pivot": blocks["temporal_audit"],
            "chemistry_history": blocks["chemistry_audit"],
            "direct_feature_count": len(refit_audit["direct_features"]),
            "thermal_feature_count": len(
                refit_audit["thermal_features"]
            ),
            "all_features_strictly_before_cutoff": True,
            "taphole_temperature_is_proxy_only": True,
            "cooling_wall_heat_loss_status": (
                "not_in_current_133_point_catalog"
            ),
        },
    )
    report = [
        "# V7 跨月稳健三路集成报告",
        "",
        (
            "- 权重（直接传感器 / 热状态残差 / 前炉历史）："
            f"{weights['direct']:.2f} / {weights['thermal']:.2f} / "
            f"{weights['history']:.2f}"
        ),
        (
            f"- 训练段模型直接测7月 MAE / ±0.02："
            f"{train_only_metrics['mae']:.6f} / "
            f"{train_only_metrics['hit_rate_abs_le_002']:.2%}"
        ),
        (
            f"- 合并训练+验证重训后7月 MAE / ±0.02 / ±0.05："
            f"{refit_metrics['mae']:.6f} / "
            f"{refit_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{refit_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        "",
        "- 权重和模型超参数均未读取7月目标。",
        "- 7月历史测试已被多版本复用，不再视为全新生产盲测。",
        "- 真实铁水温度标签仍为0行，温度/热状态概率头保持阻断。",
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
        description="训练V7跨月稳健三路Si集成。"
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
    print(
        json.dumps(
            {
                "weights": result["selected_weights"],
                "test": result["historical_test"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
