"""Read-only probe for deterministic Chinese point-name routing."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import ollama_proxy_server as proxy  # noqa: E402


QUESTIONS = (
    "查询当前顶温A、B、C、D和顶压A、B、C、D共8个点位的最新值。",
    "查一下A、B、C、D四个上升管煤气温度和压力。",
    "查一下四个顶温和四个顶压。",
    "A点顶温和A点顶压现在多少？",
)


def main() -> int:
    rows = []
    for question in QUESTIONS:
        rows.append(
            {
                "question": question,
                "variables": proxy.qa_mcp_variables(question),
                "plan": proxy.qa_mcp_sensor_query_plan(question),
            }
        )
    print(json.dumps({"ok": True, "rows": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
