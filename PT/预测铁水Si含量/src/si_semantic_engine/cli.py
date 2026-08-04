"""Command-line entrypoint for calibrated semantic Si model inference."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .engine import (
    FeatureValidationError,
    ModelConfigError,
    ModelNotCalibratedError,
    SemanticSiEngine,
)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} 的顶层必须是JSON对象")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用已标定的可解释语义神经元配置预测铁水Si分布。"
    )
    parser.add_argument("--config", type=Path, required=True, help="模型JSON配置")
    parser.add_argument(
        "--features", type=Path, required=True, help="单炉次标准化特征JSON"
    )
    parser.add_argument(
        "--pretty", action="store_true", help="用缩进格式输出预测JSON"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        engine = SemanticSiEngine.from_mapping(_load_json(args.config))
        result = engine.predict(_load_json(args.features))
    except (
        FeatureValidationError,
        ModelConfigError,
        ModelNotCalibratedError,
        OSError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            sort_keys=args.pretty,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
