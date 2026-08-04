"""CLI for building the immutable V1 heat-level experiment layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .experiment_data import build_heat_level_dataset, write_prepared_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把现有铁水Si试样级V1数据处理为固定炉次级实验数据。"
    )
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    frame = build_heat_level_dataset(
        args.labels,
        args.features,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
    )
    manifest = write_prepared_dataset(
        frame,
        args.output_dir,
        args.labels,
        args.features,
        args.train_ratio,
        args.validation_ratio,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

