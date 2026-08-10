"""Offline V19 mean-Si context ablation runner.

The runner keeps V9/V13 artifacts immutable.  It adds the V19 context blocks
only to the two LightGBM residual branches and evaluates five ablations using
the existing April/May/June time-fold contract.

Requirement: REQ-SI-V19-CONTEXT-ABLATION-20260806.
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

from .formal_dataset import sha256_file
from .train_v3 import TARGET
from .train_v7 import _assemble_features, _component_predictions
from .train_v8 import LgbmSpec, _feature_args, _fit_predict
from .train_v9 import (
    COMPONENT_NAMES,
    _blend,
    _rank_weights,
    _simplex_weights,
)
from .train_v6 import _artifact_hashes, _write_json, metrics
from .v19_context_features import context_feature_groups, merge_v19_context_features


REQUIREMENT_ID = "REQ-SI-V19-CONTEXT-ABLATION-20260806"
FIXED_WEIGHTS = {
    "direct": 0.0,
    "thermal_xgb": 0.0,
    "lgbm_huber7": 0.7,
    "lgbm_huber15_decay90": 0.2,
    "history": 0.1,
}
LGBM_SPECS = {
    "lgbm_huber7": LgbmSpec(
        "huber_leaf7_residual", "huber", 7, 35, "residual"
    ),
    "lgbm_huber15_decay90": LgbmSpec(
        "huber_leaf15_residual_decay90",
        "huber",
        15,
        45,
        "residual",
        90.0,
    ),
}
ABLATIONS = {
    "baseline": (),
    "history_si": ("history_si",),
    "pci": ("pci",),
    "chemistry": ("chemistry",),
    "all_context": ("history_si", "pci", "chemistry"),
}


def _fold_masks(combined: pd.DataFrame) -> dict[str, tuple[pd.Series, pd.Series]]:
    return {
        "2026-04": (
            combined["prediction_month"].lt("2026-04"),
            combined["prediction_month"].eq("2026-04"),
        ),
        "2026-05": (
            combined["prediction_month"].lt("2026-05"),
            combined["prediction_month"].eq("2026-05"),
        ),
        "2026-06_fixed_validation": (
            combined["experiment_split"].eq("train"),
            combined["experiment_split"].eq("validation"),
        ),
    }


def _context_columns(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    groups: dict[str, list[str]],
    selected_groups: Sequence[str],
) -> tuple[list[str], dict[str, Any]]:
    candidates = [
        column
        for group in selected_groups
        for column in groups.get(group, [])
    ]
    usable: list[str] = []
    coverage: dict[str, float] = {}
    for column in dict.fromkeys(candidates):
        if column not in combined:
            continue
        ratio = float(combined.loc[train_mask, column].notna().mean())
        coverage[column] = ratio
        if ratio >= 0.50:
            usable.append(column)
    return usable, {
        "candidate_count": len(candidates),
        "usable_count": len(usable),
        "training_coverage": coverage,
        "minimum_training_coverage": 0.50,
    }


def _component_bundle(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    evaluation_mask: pd.Series,
    *,
    feature_args: dict[str, Sequence[str]],
    context_groups_map: dict[str, list[str]],
    selected_groups: Sequence[str],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Fit unchanged V9 non-LightGBM branches and augmented LightGBM branches."""

    base_components, audit = _component_predictions(
        combined,
        train_mask,
        evaluation_mask,
        **feature_args,
    )
    train = combined.loc[train_mask]
    evaluation = combined.loc[evaluation_mask]
    extra, context_audit = _context_columns(
        combined, train_mask, context_groups_map, selected_groups
    )
    thermal_features = list(audit["thermal_features"])
    lgbm_features = list(dict.fromkeys([*thermal_features, *extra]))
    components = {
        "direct": base_components["direct"],
        "thermal_xgb": base_components["thermal"],
        "history": base_components["history"],
    }
    lgbm_models: dict[str, Any] = {}
    lgbm_feature_count: dict[str, int] = {}
    for name, spec in LGBM_SPECS.items():
        model, prediction, _ = _fit_predict(
            spec, train, evaluation, lgbm_features
        )
        lgbm_models[name] = model
        lgbm_feature_count[name] = len(lgbm_features)
        components[name] = prediction
    audit = {
        **audit,
        "lgbm_models": lgbm_models,
        "lgbm_features": lgbm_features,
        "lgbm_feature_count": lgbm_feature_count,
        "context_audit": context_audit,
        "selected_context_groups": list(selected_groups),
    }
    return components, audit


def _monthly_metrics(frame: pd.DataFrame, actual: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    months = frame["prediction_month"].astype(str).to_numpy()
    output: dict[str, Any] = {}
    for month in sorted(set(months)):
        mask = months == month
        output[month] = metrics(actual[mask], prediction[mask])
    return output


def _paired_bootstrap_delta(
    actual: np.ndarray,
    candidate: np.ndarray,
    baseline: np.ndarray,
    *,
    seed: int = 20260806,
    repeats: int = 2000,
) -> dict[str, float]:
    """Return deterministic paired bootstrap CI for candidate-baseline MAE."""

    actual = np.asarray(actual, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    baseline = np.asarray(baseline, dtype=float)
    if len(actual) == 0:
        return {"mean_delta_mae": np.nan, "ci_low": np.nan, "ci_high": np.nan}
    point = float(np.mean(np.abs(candidate - actual)) - np.mean(np.abs(baseline - actual)))
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(actual), size=(repeats, len(actual)))
    deltas = np.mean(np.abs(candidate[indexes] - actual[indexes]), axis=1) - np.mean(
        np.abs(baseline[indexes] - actual[indexes]), axis=1
    )
    return {
        "mean_delta_mae": point,
        "ci_low": float(np.quantile(deltas, 0.025)),
        "ci_high": float(np.quantile(deltas, 0.975)),
        "repeats": repeats,
    }


def _load_context(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=["official_meltno"])
    context = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    if "official_meltno" not in context:
        raise ValueError("V19上下文CSV缺少official_meltno")
    return context


def _run_ablation(
    combined: pd.DataFrame,
    feature_args: dict[str, Sequence[str]],
    context_groups_map: dict[str, list[str]],
    name: str,
    selected_groups: Sequence[str],
) -> dict[str, Any]:
    folds = _fold_masks(combined)
    fold_results: dict[str, Any] = {}
    fold_components: dict[str, dict[str, Any]] = {}
    for fold_name, (train_mask, evaluation_mask) in folds.items():
        components, audit = _component_bundle(
            combined,
            train_mask,
            evaluation_mask,
            feature_args=feature_args,
            context_groups_map=context_groups_map,
            selected_groups=selected_groups,
        )
        actual = combined.loc[evaluation_mask, TARGET].to_numpy(float)
        fold_components[fold_name] = {
            "components": components,
            "actual": actual,
            "audit": audit,
        }
        fixed_prediction = _blend(components, FIXED_WEIGHTS)
        fold_results.setdefault("fixed_weights", {})[fold_name] = metrics(
            actual, fixed_prediction
        )
        fold_results.setdefault("fixed_prediction", {})[fold_name] = fixed_prediction
    ranked = _rank_weights(
        {
            fold_name: {
                "components": item["components"],
                "actual": item["actual"],
            }
            for fold_name, item in fold_components.items()
        }
    )
    selected = ranked[0]
    train_mask = combined["experiment_split"].eq("train")
    test_mask = combined["experiment_split"].eq("test")
    test_components, test_audit = _component_bundle(
        combined,
        train_mask,
        test_mask,
        feature_args=feature_args,
        context_groups_map=context_groups_map,
        selected_groups=selected_groups,
    )
    test = combined.loc[test_mask].copy()
    actual = test[TARGET].to_numpy(float)
    fixed_prediction = _blend(test_components, FIXED_WEIGHTS)
    selected_prediction = _blend(test_components, selected["weights"])
    prediction_frame = test[["official_meltno", "prediction_cutoff_ts", "prediction_month"]].copy()
    prediction_frame["actual__Si_mean"] = actual
    prediction_frame["prediction__fixed"] = fixed_prediction
    prediction_frame["prediction__selected"] = selected_prediction
    prediction_frame["absolute_error__fixed"] = np.abs(fixed_prediction - actual)
    prediction_frame["absolute_error__selected"] = np.abs(selected_prediction - actual)
    return {
        "ablation": name,
        "context_groups": list(selected_groups),
        "pretest": {
            "fixed_weights": fold_results["fixed_weights"],
            "selected": selected,
            "ranked_top20": ranked[:20],
        },
        "historical_test": {
            "fixed_weights": metrics(actual, fixed_prediction),
            "selected": metrics(actual, selected_prediction),
            "fixed_monthly": _monthly_metrics(test, actual, fixed_prediction),
            "selected_monthly": _monthly_metrics(test, actual, selected_prediction),
        },
        "test_components": {
            component: metrics(actual, values)
            for component, values in test_components.items()
        },
        "test_predictions": prediction_frame,
        "test_audit": test_audit,
        "test_model_bundle": {
            "direct_model": test_audit["direct_model"],
            "thermal_model": test_audit["thermal_model"],
            "lgbm_models": test_audit["lgbm_models"],
            "direct_features": test_audit["direct_features"],
            "thermal_features": test_audit["thermal_features"],
            "lgbm_features": test_audit["lgbm_features"],
            "fallback": test_audit["fallback"],
            "weights": selected["weights"],
            "fixed_weights": FIXED_WEIGHTS,
            "status": "experimental_offline_v19",
            "target_column": "target__Si_mean",
            "context_groups": list(selected_groups),
        },
    }


def run_experiment(
    *,
    dataset_path: Path,
    heat_targets_path: Path,
    samples_path: Path,
    catalog_path: Path,
    temporal_dir: Path,
    context_path: Path | None,
    output_dir: Path,
) -> dict[str, Any]:
    """Run all V19 ablations and write immutable offline artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    combined, blocks = _assemble_features(
        dataset_path=dataset_path,
        heat_targets_path=heat_targets_path,
        samples_path=samples_path,
        catalog_path=catalog_path,
        temporal_dir=temporal_dir,
        target_column="target__Si_mean",
    )
    context = _load_context(context_path)
    combined = merge_v19_context_features(combined, context)
    groups = context_feature_groups(combined)
    feature_args = dict(_feature_args(blocks))
    results: dict[str, Any] = {}
    for name, selected_groups in ABLATIONS.items():
        result = _run_ablation(
            combined, feature_args, groups, name, selected_groups
        )
        prediction_path = output_dir / f"predictions_{name}.csv"
        result["test_predictions"].to_csv(
            prediction_path, index=False, encoding="utf-8-sig"
        )
        serializable = {key: value for key, value in result.items() if key != "test_predictions" and key != "test_model_bundle"}
        _write_json(output_dir / f"metrics_{name}.json", serializable)
        results[name] = result

    baseline_test = results["baseline"]["test_predictions"]["prediction__selected"].to_numpy(float)
    actual = results["baseline"]["test_predictions"]["actual__Si_mean"].to_numpy(float)
    rankings: list[dict[str, Any]] = []
    for name, result in results.items():
        candidate = result["test_predictions"]["prediction__selected"].to_numpy(float)
        rankings.append(
            {
                "ablation": name,
                "pretest_robust_mae_score": result["pretest"]["selected"]["robust_mae_score"],
                "test_mae": result["historical_test"]["selected"]["mae"],
                "test_hit_rate_abs_le_005": result["historical_test"]["selected"]["hit_rate_abs_le_005"],
                "paired_bootstrap_vs_baseline": _paired_bootstrap_delta(
                    actual, candidate, baseline_test
                ),
            }
        )
    rankings.sort(key=lambda item: (item["pretest_robust_mae_score"], item["ablation"]))
    best_name = rankings[0]["ablation"]
    best_bundle = results[best_name]["test_model_bundle"]
    joblib.dump(best_bundle, output_dir / "selected_v19_context_ensemble.joblib")
    pd.DataFrame(rankings).to_csv(
        output_dir / "ablation_comparison.csv", index=False, encoding="utf-8-sig"
    )
    coverage = {
        group: {
            column: float(combined[column].notna().mean())
            for column in columns
            if column in combined
        }
        for group, columns in groups.items()
    }
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v19",
        "target_column": "target__Si_mean",
        "training_rows": int(combined["experiment_split"].eq("train").sum()),
        "validation_rows": int(combined["experiment_split"].eq("validation").sum()),
        "test_rows": int(combined["experiment_split"].eq("test").sum()),
        "ablation_order": list(ABLATIONS),
        "selected_candidate": best_name,
        "rankings": rankings,
        "context_feature_coverage": coverage,
        "chemistry_lineage_status": "time_background_only_unverified_batch_to_heat_lineage",
        "selection_contract": "April/May expanding folds plus fixed June validation; July test read after selection",
        "inputs": {
            "dataset": sha256_file(dataset_path),
            "heat_targets": sha256_file(heat_targets_path),
            "samples": sha256_file(samples_path),
            "sensor_catalog": sha256_file(catalog_path),
            "temporal_manifest": sha256_file(temporal_dir / "manifest.json"),
            "context": sha256_file(context_path) if context_path else None,
        },
        "runtime": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
        },
    }
    _write_json(output_dir / "metrics.json", result)
    _write_json(output_dir / "feature_contract.json", {
        "requirement_id": REQUIREMENT_ID,
        "context_groups": groups,
        "coverage": coverage,
        "all_features_strictly_before_cutoff": True,
        "new_features_only_in_lightgbm_residual_branches": True,
        "chemistry_lineage_status": result["chemistry_lineage_status"],
    })
    _write_json(output_dir / "run_manifest.json", {
        "requirement_id": REQUIREMENT_ID,
        "inputs": result["inputs"],
        "artifacts": _artifact_hashes(output_dir),
    })
    (output_dir / "report.md").write_text(
        "# V19 平均Si上下文特征消融实验\n\n"
        f"- 选择候选：`{best_name}`\n"
        f"- 训练/验证/测试：{result['training_rows']}/{result['validation_rows']}/{result['test_rows']}\n"
        "- 炉料化学仅作为发布时间背景特征，未建立批次到炉次谱系。\n"
        "- 所有产物保持离线实验状态，未替换V9/V13或生产接口。\n",
        encoding="utf-8",
    )
    return result


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="运行平均Si V19上下文特征消融实验。")
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--heat-targets", type=Path, required=True)
    cli.add_argument("--samples", type=Path, required=True)
    cli.add_argument("--sensor-catalog", type=Path, required=True)
    cli.add_argument("--temporal-dir", type=Path, required=True)
    cli.add_argument("--context", type=Path, default=None)
    cli.add_argument("--output-dir", type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result = run_experiment(
        dataset_path=args.dataset.resolve(),
        heat_targets_path=args.heat_targets.resolve(),
        samples_path=args.samples.resolve(),
        catalog_path=args.sensor_catalog.resolve(),
        temporal_dir=args.temporal_dir.resolve(),
        context_path=args.context.resolve() if args.context else None,
        output_dir=args.output_dir.resolve(),
    )
    print(json.dumps({"ok": True, "selected_candidate": result["selected_candidate"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
