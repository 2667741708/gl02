#!/usr/bin/env python3
"""Run the local cohesive-zone intelligent diagnosis on a CSV file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from 炉况规则引擎.features.cohesive_zone_intelligent_diagnosis import (  # noqa: E402
    diagnose_cohesive_zone_movement,
    estimate_and_diagnose_cohesive_zone,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从一分钟CSV构建软熔带移动特征并输出上移/稳定/下移智能诊断。"
    )
    parser.add_argument("--input", required=True, help="输入CSV路径。")
    parser.add_argument(
        "--timestamp-column",
        default="timestamp",
        help="时间列名，默认timestamp。",
    )
    parser.add_argument("--evaluation-time", help="历史评价截止时间；默认使用最后一行。")
    parser.add_argument("--config", help="可选诊断YAML覆盖路径。")
    parser.add_argument("--estimator-config", help="可选C2几何估算器YAML覆盖路径。")
    parser.add_argument(
        "--include-geometry",
        action="store_true",
        help="同时运行现有C2根部几何估算器并输出方向一致性。",
    )
    parser.add_argument("--output", help="可选UTF-8 JSON输出路径；默认打印到标准输出。")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for REQ-COHESIVE-ZONE-INTELLIGENT-DIAGNOSIS-20260810."""
    args = _build_parser().parse_args(argv)
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"input CSV not found: {input_path}")
    frame = pd.read_csv(input_path)
    if args.timestamp_column not in frame.columns:
        raise ValueError(f"timestamp column not found: {args.timestamp_column}")
    frame[args.timestamp_column] = pd.to_datetime(
        frame[args.timestamp_column], errors="coerce"
    )
    frame = frame.loc[frame[args.timestamp_column].notna()].copy()
    frame = frame.set_index(args.timestamp_column)
    if args.include_geometry:
        result = estimate_and_diagnose_cohesive_zone(
            frame,
            evaluation_time=args.evaluation_time,
            estimator_config_path=args.estimator_config,
            diagnosis_config_path=args.config,
        )
        available = result["intelligent_diagnosis"].get("status") == "available"
    else:
        result = diagnose_cohesive_zone_movement(
            frame,
            evaluation_time=args.evaluation_time,
            config_path=args.config,
        )
        available = result.get("status") == "available"
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if available else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
