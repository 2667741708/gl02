"""Fit and save one V19 ablation bundle for offline replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import joblib
import pandas as pd

from .train_v7 import _assemble_features
from .train_v8 import _feature_args
from .train_v19 import ABLATIONS, _run_ablation
from .v19_context_features import context_feature_groups, merge_v19_context_features


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="保存一个V19消融模型供离线回放。")
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--heat-targets", type=Path, required=True)
    cli.add_argument("--samples", type=Path, required=True)
    cli.add_argument("--sensor-catalog", type=Path, required=True)
    cli.add_argument("--temporal-dir", type=Path, required=True)
    cli.add_argument("--context", type=Path, required=True)
    cli.add_argument("--ablation", choices=tuple(ABLATIONS), required=True)
    cli.add_argument("--output", type=Path, required=True)
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    combined, blocks = _assemble_features(
        dataset_path=args.dataset.resolve(), heat_targets_path=args.heat_targets.resolve(),
        samples_path=args.samples.resolve(), catalog_path=args.sensor_catalog.resolve(),
        temporal_dir=args.temporal_dir.resolve(), target_column="target__Si_mean",
    )
    context = pd.read_csv(args.context.resolve(), low_memory=False, encoding="utf-8-sig")
    combined = merge_v19_context_features(combined, context)
    result = _run_ablation(
        combined, dict(_feature_args(blocks)), context_feature_groups(combined),
        args.ablation, ABLATIONS[args.ablation],
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(result["test_model_bundle"], output)
    result["test_predictions"].to_csv(output.with_name(output.stem + "_test_predictions.csv"), index=False, encoding="utf-8-sig")
    output.with_suffix(".metrics.json").write_text(json.dumps({"ablation": args.ablation, "pretest": result["pretest"], "historical_test": result["historical_test"], "test_components": result["test_components"]}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"ok": True, "ablation": args.ablation, "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
