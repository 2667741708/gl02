"""完整调控结论生成引擎命令行入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from recommendation.core import RecommendationEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="根据标准炉况诊断JSON生成只读调控建议")
    parser.add_argument("diagnosis_json", help="标准炉况诊断JSON文件")
    parser.add_argument("--output", default="", help="可选输出JSON文件；默认打印到终端")
    args = parser.parse_args()
    diagnosis = json.loads(Path(args.diagnosis_json).read_text(encoding="utf-8"))
    recommendation = RecommendationEngine().generate(diagnosis)
    text = json.dumps(recommendation, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
