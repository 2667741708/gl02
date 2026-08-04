"""Fast Plain CatBoost comparison after V17 Ordered runtime failures.

Requirement:
    REQ-SI-CATBOOST-PLAIN-V18-20260727
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .train_v17 import CatSpec, run_experiment


REQUIREMENT_ID = "REQ-SI-CATBOOST-PLAIN-V18-20260727"


def _specs() -> tuple[CatSpec, ...]:
    return (
        CatSpec(
            name="plain_mae_d6_residual",
            loss_function="MAE",
            depth=6,
            target_mode="residual",
            boosting_type="Plain",
            iterations=200,
            learning_rate=0.04,
        ),
        CatSpec(
            name="plain_rmse_d6_residual",
            loss_function="RMSE",
            depth=6,
            target_mode="residual",
            boosting_type="Plain",
            iterations=200,
            learning_rate=0.04,
        ),
    )


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="训练V18快速Plain CatBoost残差模型。"
    )
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--heat-targets", type=Path, required=True)
    cli.add_argument("--samples", type=Path, required=True)
    cli.add_argument("--sensor-catalog", type=Path, required=True)
    cli.add_argument("--temporal-dir", type=Path, required=True)
    cli.add_argument(
        "--v13-selection-audit", type=Path, required=True
    )
    cli.add_argument("--v13-run-manifest", type=Path, required=True)
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
        v13_selection_audit_path=args.v13_selection_audit,
        v13_run_manifest_path=args.v13_run_manifest,
        output_dir=args.output_dir,
        specs=_specs(),
        requirement_id=REQUIREMENT_ID,
        model_version="v18",
        report_title="V18 CatBoost快速Plain提升报告",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
