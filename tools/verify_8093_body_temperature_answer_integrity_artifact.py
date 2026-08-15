"""Offline contract verification for a remote-baseline 8093 proxy artifact."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
MCP_DIR = ROOT / "高炉前端数据" / "智能助手" / "mcp"
DIAGNOSIS_DIR = ROOT / "自动诊断服务"


def load_proxy(path: Path):
    for item in (BACKEND, MCP_DIR, DIAGNOSIS_DIR):
        if str(item) not in sys.path:
            sys.path.insert(0, str(item))
    spec = importlib.util.spec_from_file_location("verified_8093_proxy_artifact", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load artifact: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    source = artifact.read_text(encoding="utf-8")
    compile(source, str(artifact), "exec")
    proxy = load_proxy(artifact)

    prompts = (
        "查询最近一小时第7层到第13层各层A到H的平均温度、总体标准差、最高、最低和极差，并比较15分钟滚动标准差是增大还是减小。",
        "比较最近两小时第7层到第13层每层平均温度的波动，列出各层覆盖率、极差、变化量、斜率和变异系数。",
        "查询今天8点到9点第7层到第13层各层平均温度，指出哪一层波动最大，并列出判断依据。",
    )
    plans = [proxy.qa_mcp_sensor_query_plan(prompt) for prompt in prompts]
    assert all(plan and plan["tool"] == "gl02ext__query_body_temperature_statistics" for plan in plans)
    assert all(plan["arguments"]["start_layer"] == 7 for plan in plans)
    assert all(plan["arguments"]["end_layer"] == 13 for plan in plans)

    point_plan = proxy.qa_mcp_sensor_query_plan(
        "查询最近30分钟第12层A到H各方位温度，并给出第12层的空间平均温度和最大温差。"
    )
    assert point_plan["arguments"]["include_point_statistics"] is True

    payload = {
        "ok": True,
        "start_time": "2026-08-14T16:00:00+08:00",
        "end_time": "2026-08-14T16:30:00+08:00",
        "unit": "℃",
        "positions": list("AB"),
        "layer_statistics": [{
            "layer": 12,
            "expected_minute_count": 31,
            "statistics": {"count": 30, "avg": 45, "range": 2},
        }],
        "point_statistics": [
            {"layer": 12, "position": "A", "expected_minute_count": 31,
             "coverage_ratio": 30 / 31,
             "statistics": {"count": 30, "avg": 44, "stddev_pop": 1, "min": 42, "max": 46, "range": 4}},
            {"layer": 12, "position": "B", "expected_minute_count": 31,
             "coverage_ratio": 29 / 31,
             "statistics": {"count": 29, "avg": 46, "stddev_pop": 2, "min": 41, "max": 49, "range": 8}},
        ],
        "data_quality": {"raw_row_count": 59, "expected_rows": 62, "missing_row_count": 3},
        "source": {"service": "blast-furnace-gl02-extended-mcp", "schema": "bf_sensor", "object": "one_minute_values"},
    }
    answer = proxy.deterministic_mcp_answer(
        "gl02ext__query_body_temperature_statistics",
        json.dumps({"result": payload}, ensure_ascii=False),
    )
    for token in ("第12层A方位", "平均 44℃", "第12层B方位", "平均 46℃", "第12层空间平均"):
        assert token in answer

    large = {"ok": True, "padding": "x" * (proxy.QA_MCP_MAX_RESULT_CHARS + 100)}
    preserved = proxy.mcp_result_to_text(SimpleNamespace(structuredContent=large), max_chars=None)
    assert json.loads(preserved) == large
    assert "build_score_explanation" in source
    assert "build_a_score_explanation(" not in source
    assert "body_statistics_plan = qa_mcp_body_temperature_statistics_plan(question)" in source
    assert "if body_statistics_plan is not None" in source
    assert "sensor_plan = body_statistics_plan or qa_mcp_sensor_query_plan(question)" in source
    print(json.dumps({"ok": True, "artifact": str(artifact), "prompt_count": len(prompts), "point_values": [44, 46]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
