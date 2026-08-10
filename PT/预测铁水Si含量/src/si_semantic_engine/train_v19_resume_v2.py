"""Resumable V19 runner without placeholder model artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from .train_v7 import _assemble_features
from .train_v8 import _feature_args
from .train_v19 import ABLATIONS, _run_ablation
from .v19_context_features import context_feature_groups, merge_v19_context_features


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="断点续跑V19平均Si上下文消融。")
    for name in ("dataset", "heat_targets", "samples", "sensor_catalog", "temporal_dir", "context", "output_dir"):
        cli.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    cli.add_argument("--ablations", nargs="+", choices=tuple(ABLATIONS), default=tuple(ABLATIONS))
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    combined, blocks = _assemble_features(
        dataset_path=args.dataset.resolve(), heat_targets_path=args.heat_targets.resolve(),
        samples_path=args.samples.resolve(), catalog_path=args.sensor_catalog.resolve(),
        temporal_dir=args.temporal_dir.resolve(), target_column="target__Si_mean",
    )
    context = pd.read_csv(args.context.resolve(), low_memory=False, encoding="utf-8-sig")
    combined = merge_v19_context_features(combined, context)
    groups = context_feature_groups(combined)
    feature_args = dict(_feature_args(blocks))
    completed: list[str] = []
    for name in args.ablations:
        metrics_path = args.output_dir / f"metrics_{name}.json"
        prediction_path = args.output_dir / f"predictions_{name}.csv"
        if metrics_path.exists() and prediction_path.exists():
            completed.append(name)
            continue
        result = _run_ablation(combined, feature_args, groups, name, ABLATIONS[name])
        predictions = result.pop("test_predictions")
        result.pop("test_model_bundle", None)
        predictions.to_csv(prediction_path, index=False, encoding="utf-8-sig")
        metrics_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        completed.append(name)
        (args.output_dir / "resume_state.json").write_text(json.dumps({"completed": completed}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "completed": completed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
