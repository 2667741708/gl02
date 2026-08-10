"""Offline V19 rolling update: train through July, test on August."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd

from .prospective import build_inference_feature_frame
from .train_v19 import (
    ABLATIONS,
    FIXED_WEIGHTS,
    REQUIREMENT_ID,
    TARGET,
    _blend,
    _component_bundle,
    _monthly_metrics,
    _paired_bootstrap_delta,
    _rank_weights,
    _write_json,
    metrics,
)
from .train_v7 import _assemble_features
from .train_v8 import _feature_args
from .v19_context_features import context_feature_groups, merge_v19_context_features


def _rolling_folds(frame: pd.DataFrame, july_end: pd.Timestamp) -> dict[str, tuple[pd.Series, pd.Series]]:
    cutoff = pd.to_datetime(frame["prediction_cutoff_ts"])
    july_eval = (cutoff >= pd.Timestamp("2026-07-01")) & (cutoff <= july_end)
    return {
        "2026-04": (cutoff < pd.Timestamp("2026-04-01"), cutoff.to_period("M") == "2026-04"),
        "2026-05": (cutoff < pd.Timestamp("2026-05-01"), cutoff.to_period("M") == "2026-05"),
        "2026-06": (cutoff < pd.Timestamp("2026-06-01"), cutoff.to_period("M") == "2026-06"),
        "2026-07_validation": (cutoff < pd.Timestamp("2026-07-01"), july_eval),
    }


def _run_one(frame: pd.DataFrame, feature_args: dict[str, Sequence[str]], groups: dict[str, list[str]], name: str, selected_groups: Sequence[str], july_end: pd.Timestamp) -> dict[str, Any]:
    folds: dict[str, Any] = {}
    fold_components: dict[str, Any] = {}
    for fold_name, (train_mask, evaluation_mask) in _rolling_folds(frame, july_end).items():
        if int(train_mask.sum()) == 0 or int(evaluation_mask.sum()) == 0:
            continue
        components, audit = _component_bundle(frame, train_mask, evaluation_mask, feature_args=feature_args, context_groups_map=groups, selected_groups=selected_groups)
        actual = frame.loc[evaluation_mask, TARGET].to_numpy(float)
        fold_components[fold_name] = {"components": components, "actual": actual, "audit": audit}
        fixed = _blend(components, FIXED_WEIGHTS)
        folds[fold_name] = metrics(actual, fixed)
    ranked = _rank_weights({k: {"components": v["components"], "actual": v["actual"]} for k, v in fold_components.items()})
    selected = ranked[0]
    train_mask = frame["experiment_split"].eq("train")
    test_mask = frame["experiment_split"].eq("test")
    test_components, test_audit = _component_bundle(frame, train_mask, test_mask, feature_args=feature_args, context_groups_map=groups, selected_groups=selected_groups)
    test = frame.loc[test_mask].copy()
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
        "pretest": {"fixed_weights": folds, "selected": selected, "ranked_top20": ranked[:20]},
        "historical_test": {"fixed_weights": metrics(actual, fixed_prediction), "selected": metrics(actual, selected_prediction), "fixed_monthly": _monthly_metrics(test, actual, fixed_prediction), "selected_monthly": _monthly_metrics(test, actual, selected_prediction)},
        "test_components": {component: metrics(actual, values) for component, values in test_components.items()},
        "test_predictions": prediction_frame,
        "test_audit": test_audit,
        "test_model_bundle": {
            "direct_model": test_audit["direct_model"], "thermal_model": test_audit["thermal_model"], "lgbm_models": test_audit["lgbm_models"],
            "direct_features": test_audit["direct_features"], "thermal_features": test_audit["thermal_features"], "lgbm_features": test_audit["lgbm_features"],
            "fallback": test_audit["fallback"], "weights": selected["weights"], "fixed_weights": FIXED_WEIGHTS,
            "status": "experimental_offline_v19_august_holdout", "target_column": TARGET, "context_groups": list(selected_groups),
        },
    }


def _load_augmented(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, Sequence[str]], dict[str, Any]]:
    formal, blocks = _assemble_features(dataset_path=args.dataset.resolve(), heat_targets_path=args.heat_targets.resolve(), samples_path=args.samples.resolve(), catalog_path=args.catalog.resolve(), temporal_dir=args.temporal_dir.resolve(), target_column=TARGET)
    recent_rows = pd.read_csv(args.recent_rows.resolve(), low_memory=False, encoding="utf-8-sig")
    all_targets = pd.concat([pd.read_csv(args.heat_targets.resolve(), low_memory=False), pd.read_csv(args.recent_targets.resolve(), low_memory=False)], ignore_index=True).drop_duplicates("official_meltno", keep="last")
    all_samples = pd.concat([pd.read_csv(args.samples.resolve(), low_memory=False), pd.read_csv(args.recent_samples.resolve(), low_memory=False)], ignore_index=True)
    recent, _ = build_inference_feature_frame(recent_rows, all_targets, all_samples, args.catalog.resolve(), args.recent_temporal_dir.resolve())
    target_cols = [c for c in all_targets.columns if c.startswith("target__") or c in {"official_meltno", "open_ts", "close_ts", "label_first_result_ts", "result_at_or_before_cutoff_count", "tank_no_count", "tank_nos", "taphole_id_count", "taphole_ids", "representative_target_definition", "distribution_target_definition", "contract_version"}]
    recent = recent.merge(all_targets[[c for c in target_cols if c in all_targets]], on="official_meltno", how="left", suffixes=("", "_target"))
    july_end = pd.to_datetime(formal["prediction_cutoff_ts"]).max()
    recent = recent[pd.to_datetime(recent["prediction_cutoff_ts"]) > july_end].copy()
    formal = formal.copy()
    combined = pd.concat([formal, recent], ignore_index=True, sort=False)
    combined["prediction_cutoff_ts"] = pd.to_datetime(combined["prediction_cutoff_ts"], errors="raise")
    combined["prediction_month"] = combined["prediction_cutoff_ts"].dt.to_period("M").astype(str)
    combined["experiment_split"] = np.where(combined["prediction_cutoff_ts"] <= july_end, "train", "test")
    context = pd.concat([pd.read_csv(args.context.resolve(), low_memory=False), pd.read_csv(args.recent_context.resolve(), low_memory=False)], ignore_index=True).drop_duplicates("official_meltno", keep="last")
    combined = merge_v19_context_features(combined, context)
    groups = context_feature_groups(combined)
    return combined, dict(_feature_args(blocks)), {"july_end": july_end, "groups": groups, "formal_rows": len(formal), "august_rows": int((combined["experiment_split"] == "test").sum())}


def main(argv: Sequence[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "heat_targets", "samples", "catalog", "temporal_dir", "context", "recent_rows", "recent_targets", "recent_samples", "recent_temporal_dir", "recent_context", "output_dir"):
        cli.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    args = cli.parse_args(argv)
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    frame, feature_args, audit = _load_augmented(args)
    results = {}
    for name, selected_groups in ABLATIONS.items():
        result = _run_one(frame, feature_args, audit["groups"], name, selected_groups, audit["july_end"])
        result["test_predictions"].to_csv(output / f"predictions_{name}.csv", index=False, encoding="utf-8-sig")
        _write_json(output / f"metrics_{name}.json", {k: v for k, v in result.items() if k not in {"test_predictions", "test_model_bundle"}})
        results[name] = result
    baseline = results["baseline"]["test_predictions"]["prediction__selected"].to_numpy(float)
    actual = results["baseline"]["test_predictions"]["actual__Si_mean"].to_numpy(float)
    rankings = []
    for name, result in results.items():
        pred = result["test_predictions"]["prediction__selected"].to_numpy(float)
        rankings.append({"ablation": name, "pretest_robust_mae_score": result["pretest"]["selected"]["robust_mae_score"], "test_mae": result["historical_test"]["selected"]["mae"], "test_hit_rate_abs_le_005": result["historical_test"]["selected"]["hit_rate_abs_le_005"], "paired_bootstrap_vs_baseline": _paired_bootstrap_delta(actual, pred, baseline)})
    rankings.sort(key=lambda item: (item["pretest_robust_mae_score"], item["ablation"]))
    selected_name = rankings[0]["ablation"]
    joblib.dump(results[selected_name]["test_model_bundle"], output / "selected_v19_august_holdout.joblib")
    pd.DataFrame(rankings).to_csv(output / "ablation_comparison.csv", index=False, encoding="utf-8-sig")
    summary = {"requirement_id": REQUIREMENT_ID, "model_status": "experimental_offline_v19_august_holdout", "training_rows": int((frame["experiment_split"] == "train").sum()), "test_rows": int((frame["experiment_split"] == "test").sum()), "july_end": str(audit["july_end"]), "selected_candidate": selected_name, "rankings": rankings, "source_audit": audit}
    _write_json(output / "metrics.json", summary)
    (output / "report.md").write_text("# V19 7月训练/8月时间外测试\n\n- 状态：`experimental_offline`。\n- 7月数据纳入训练，8月新增炉次作为时间外测试。\n- 候选选择仅使用4月、5月、6月和7月验证；未写生产接口。\n- 详细指标见 `metrics.json`、`ablation_comparison.csv` 与各组 `metrics_*.json`。\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
