"""Train and audit multi-window semantic Si V5 candidates.

Candidate selection uses only the fixed chronological validation segment.
The locked test is evaluated after selection.  Expanding-month backtests
rebuild the training-only feature ranking inside every fold.

Requirement:
    REQ-SI-TEMPORAL-SEMANTIC-V5-20260727
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
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline

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


REQUIREMENT_ID = "REQ-SI-TEMPORAL-SEMANTIC-V5-20260727"
RANDOM_STATE = 20260726


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
    residual = np.asarray(predicted) - np.asarray(actual)
    return {
        "rows": int(len(actual)),
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "bias": float(np.mean(residual)),
        "hit_rate_abs_le_002": float(np.mean(np.abs(residual) <= 0.02)),
        "hit_rate_abs_le_005": float(np.mean(np.abs(residual) <= 0.05)),
        "hit_rate_abs_le_010": float(np.mean(np.abs(residual) <= 0.10)),
    }


def _model() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                ExtraTreesRegressor(
                    n_estimators=400,
                    min_samples_leaf=2,
                    max_features=0.50,
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def _select_importance_features(
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
        n_estimators=300,
        min_samples_leaf=3,
        max_features=0.70,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    selector.fit(values, train[TARGET].to_numpy(float))
    order = np.argsort(selector.feature_importances_)[::-1]
    return [usable[index] for index in order[: min(top_k, len(order))]]


def _label_stability(samples_path: Path) -> dict[str, Any]:
    samples = pd.read_csv(
        samples_path,
        usecols=["official_meltno", "si_pct"],
        encoding="utf-8-sig",
    ).dropna()
    leave_one_out: list[float] = []
    pairwise: list[float] = []
    bootstrap_std: list[float] = []
    rng = np.random.default_rng(RANDOM_STATE)
    for values in samples.groupby("official_meltno")["si_pct"]:
        array = values[1].to_numpy(float)
        if len(array) < 2:
            continue
        center = float(np.median(array))
        leave_one_out.extend(
            abs(float(np.median(np.delete(array, index))) - center)
            for index in range(len(array))
        )
        pairwise.extend(
            abs(float(array[left] - array[right]))
            for left in range(len(array))
            for right in range(left + 1, len(array))
        )
        bootstrap = np.median(
            rng.choice(array, size=(500, len(array)), replace=True),
            axis=1,
        )
        bootstrap_std.append(float(np.std(bootstrap, ddof=1)))

    def summarize(values: Sequence[float]) -> dict[str, float]:
        array = np.asarray(values, dtype=float)
        return {
            "rows": int(len(array)),
            "mean": float(np.mean(array)),
            "median": float(np.median(array)),
            "p75": float(np.quantile(array, 0.75)),
            "p90": float(np.quantile(array, 0.90)),
            "ratio_abs_le_002": float(np.mean(array <= 0.02)),
        }

    return {
        "interpretation": (
            "diagnostic of representative-label stability, not a formal "
            "irreducible-error proof"
        ),
        "leave_one_sample_out_median_change": summarize(leave_one_out),
        "within_heat_pairwise_sample_abs_difference": summarize(pairwise),
        "bootstrap_median_standard_deviation_by_heat": summarize(
            bootstrap_std
        ),
    }


def _candidate_features(
    combined: pd.DataFrame,
    train_mask: pd.Series,
    base_history: Sequence[str],
    temporal_columns: Sequence[str],
    spatial_columns: Sequence[str],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    train = combined.loc[train_mask]
    temporal_ranked, temporal_ranking = select_train_correlated_features(
        train,
        train[TARGET],
        temporal_columns,
        top_k=len(temporal_columns),
    )
    spatial_ranked, spatial_ranking = select_train_correlated_features(
        train,
        train[TARGET],
        spatial_columns,
        top_k=len(spatial_columns),
    )
    candidates = {
        "base_history": list(base_history),
        "base_history_importance250": _select_importance_features(
            train, base_history, top_k=250
        ),
    }
    for top_k in (100, 250, 500, 1000):
        candidates[f"base_history_temporal_spearman{top_k}"] = list(
            dict.fromkeys(
                [*base_history, *temporal_ranked[:top_k]]
            )
        )
    for top_k in (250, 500):
        candidates[f"base_history_spatial_spearman{top_k}"] = list(
            dict.fromkeys([*base_history, *spatial_ranked[:top_k]])
        )
    return candidates, {
        "selection_rows": int(train_mask.sum()),
        "selection_scope": "training_split_only",
        "temporal_eligible": len(temporal_ranked),
        "spatial_eligible": len(spatial_ranked),
        "temporal_ranking_top200": temporal_ranking.head(200).to_dict(
            "records"
        ),
        "spatial_ranking_top200": spatial_ranking.head(200).to_dict(
            "records"
        ),
    }


def _rolling_month_backtest(
    combined: pd.DataFrame,
    *,
    base_history: Sequence[str],
    temporal_columns: Sequence[str],
    temporal_top_k: int,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    months = combined["prediction_month"].drop_duplicates().tolist()
    for target_month in months:
        test_mask = combined["prediction_month"].eq(target_month)
        train_mask = combined["prediction_month"].lt(target_month)
        if int(train_mask.sum()) < 500 or int(test_mask.sum()) < 10:
            continue
        train = combined.loc[train_mask]
        ranked, _ = select_train_correlated_features(
            train,
            train[TARGET],
            temporal_columns,
            top_k=temporal_top_k,
        )
        features = list(dict.fromkeys([*base_history, *ranked]))
        model = _model()
        model.fit(train[features], train[TARGET].to_numpy(float))
        test = combined.loc[test_mask]
        prediction = model.predict(test[features])
        output[str(target_month)] = {
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_end": str(
                train["prediction_cutoff_ts"].max()
            ),
            "test_start": str(test["prediction_cutoff_ts"].min()),
            "feature_count": len(features),
            "metrics": metrics(
                test[TARGET].to_numpy(float), prediction
            ),
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
    temporal, temporal_audit = pivot_temporal_statistics(
        temporal_long, frame
    )
    spatial = derive_temporal_spatial_neurons(temporal).replace(
        [np.inf, -np.inf], np.nan
    )
    combined = pd.concat(
        [frame, *v4_blocks.values(), temporal, spatial], axis=1
    )
    train_mask = combined["experiment_split"].eq("train")
    validation_mask = combined["experiment_split"].eq("validation")
    test_mask = combined["experiment_split"].eq("test")
    v4_feature_sets, _ = _feature_sets(
        combined,
        train_mask,
        {name: list(block.columns) for name, block in v4_blocks.items()},
    )
    base_history = v4_feature_sets["v3_plus_history"]
    candidates, ranking_audit = _candidate_features(
        combined,
        train_mask,
        base_history,
        list(temporal.columns),
        list(spatial.columns),
    )

    train = combined.loc[train_mask]
    validation = combined.loc[validation_mask]
    validation_results: dict[str, Any] = {}
    fitted: dict[str, Pipeline] = {}
    for name, features in candidates.items():
        model = _model()
        model.fit(train[features], train[TARGET].to_numpy(float))
        prediction = model.predict(validation[features])
        validation_results[name] = {
            "feature_count": len(features),
            "metrics": metrics(
                validation[TARGET].to_numpy(float), prediction
            ),
        }
        fitted[name] = model
    selected_name = min(
        validation_results,
        key=lambda name: (
            validation_results[name]["metrics"]["mae"],
            -validation_results[name]["metrics"][
                "hit_rate_abs_le_002"
            ],
            name,
        ),
    )
    selected_model = fitted[selected_name]
    selected_features = candidates[selected_name]
    test = combined.loc[test_mask].copy()
    test_prediction = selected_model.predict(test[selected_features])
    test_metrics = metrics(test[TARGET].to_numpy(float), test_prediction)
    test_output = test[
        ["official_meltno", "prediction_cutoff_ts", TARGET]
    ].copy()
    test_output["prediction__Si_representative"] = test_prediction
    test_output["absolute_error"] = np.abs(
        test_output[TARGET]
        - test_output["prediction__Si_representative"]
    )
    test_output.to_csv(
        output_dir / "predictions_test.csv",
        index=False,
        encoding="utf-8-sig",
    )
    joblib.dump(
        {
            "model": selected_model,
            "features": selected_features,
            "candidate": selected_name,
            "status": "experimental_offline_v5",
        },
        models_dir / "selected_v5.joblib",
    )
    importance = selected_model.named_steps["model"].feature_importances_
    feature_importance = sorted(
        (
            {"feature": feature, "importance": float(value)}
            for feature, value in zip(selected_features, importance)
        ),
        key=lambda item: item["importance"],
        reverse=True,
    )
    _write_json(
        output_dir / "feature_importance.json", feature_importance[:300]
    )
    _write_json(output_dir / "ranking_audit.json", ranking_audit)

    temporal_top_k = (
        int(selected_name.rsplit("spearman", 1)[1])
        if "temporal_spearman" in selected_name
        else 250
    )
    rolling = _rolling_month_backtest(
        combined,
        base_history=base_history,
        temporal_columns=list(temporal.columns),
        temporal_top_k=temporal_top_k,
    )
    label_stability = _label_stability(samples_path)
    result = {
        "requirement_id": REQUIREMENT_ID,
        "model_status": "experimental_offline_v5",
        "selection_contract": (
            "all candidates selected on fixed validation; locked test read "
            "only after selection"
        ),
        "validation_candidates": validation_results,
        "selected": {
            "candidate": selected_name,
            "feature_count": len(selected_features),
            "validation": validation_results[selected_name]["metrics"],
            "test": test_metrics,
        },
        "rolling_month_backtest": rolling,
        "label_stability": label_stability,
        "goal": {
            "mae_target": 0.02,
            "tolerance_target": 0.02,
            "status": (
                "reached"
                if test_metrics["mae"] <= 0.02
                else "not_reached"
            ),
        },
    }
    _write_json(output_dir / "metrics.json", result)
    _write_json(
        output_dir / "feature_contract.json",
        {
            "selected_features": selected_features,
            "v4_derivation": v4_audit,
            "temporal_pivot": temporal_audit,
            "temporal_source_manifest": {
                "requirement_id": temporal_manifest["requirement_id"],
                "total_rows": temporal_manifest["total_rows"],
                "parts": len(temporal_manifest["parts"]),
            },
        },
    )
    report = [
        "# V5 多窗口语义神经元训练报告",
        "",
        f"- 选中候选：`{selected_name}`",
        f"- 特征数：{len(selected_features)}",
        (
            f"- 验证 MAE / ±0.02："
            f"{validation_results[selected_name]['metrics']['mae']:.6f} / "
            f"{validation_results[selected_name]['metrics']['hit_rate_abs_le_002']:.2%}"
        ),
        (
            f"- 锁定测试 MAE / ±0.02 / ±0.05："
            f"{test_metrics['mae']:.6f} / "
            f"{test_metrics['hit_rate_abs_le_002']:.2%} / "
            f"{test_metrics['hit_rate_abs_le_005']:.2%}"
        ),
        (
            "- 留一试样导致整炉中位数变化的平均绝对值："
            f"{label_stability['leave_one_sample_out_median_change']['mean']:.6f}% Si"
        ),
        (
            "- 每炉 bootstrap 中位数标准差均值："
            f"{label_stability['bootstrap_median_standard_deviation_by_heat']['mean']:.6f}% Si"
        ),
        "",
        "- 当前仍是离线实验，未达到0.02目标，禁止接生产MCP。",
        "- 标签稳定性只是瓶颈诊断，不等同于严格不可约误差下界。",
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
        "selected_candidate": selected_name,
        "selected_feature_count": len(selected_features),
        "artifacts": _artifact_hashes(output_dir),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_json(output_dir / "sha256sums.json", _artifact_hashes(output_dir))
    return result


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="训练多窗口语义神经元Si V5离线模型。"
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
