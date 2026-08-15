"""Evaluate three production MCP sensor-reasoning contracts without retries.

The suite sends at most one SSE request per selected case.  It separates MCP
execution success from final-answer completeness and independently recomputes
the numerical checks exposed by the tool payloads.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from probe_8093_cross_mcp_computation import run_once


CASES = {
    "T1": (
        "传感器证据推断",
        "[MCP评估T1] 请调用工具读取顶压和全炉压差两个传感器（不是凭知识回答），"
        "列出工具返回的数据时间和数值，然后由模型判断这些证据是否足以推测压力状态；"
        "若不足，明确还需要哪种时间序列，禁止编造。",
    ),
    "T2": (
        "统计与独立复算",
        "[MCP评估T2] 请调用传感器统计工具查询顶压 P_top 最近1小时数据，返回起止时间、"
        "样本数、均值、总体标准差、极差、首末值、变化量和斜率；再计算变异系数 "
        "CV=标准差÷均值×100%，不要省略公式。",
    ),
    "T3": (
        "跨 MCP 多工具与计算工具",
        "[MCP评估T3] 请先查询上一炉铁水Si平均值，再调用相关性计算工具分析最近1小时"
        "顶压 P_top 与全炉压差 DP_total 的 Pearson 相关系数和对齐样本数；最后让模型结合"
        "两个MCP工具的结果说明相关性强弱。必须列出工具来源、原始值和计算证据，"
        "禁止把相关性说成因果。",
    ),
}


def _tool_payload(result: dict[str, Any], tool: str) -> dict[str, Any]:
    for item in result.get("tool_results") or []:
        if item.get("tool") == tool and isinstance(item.get("result"), dict):
            return item["result"]
    for item in result.get("source_status") or []:
        if item.get("tool") != tool:
            continue
        try:
            parsed = json.loads(str(item.get("result_text") or ""))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _sensor_item(payload: dict[str, Any], variable: str) -> dict[str, Any]:
    for item in payload.get("items") or []:
        if item.get("requested_variable") == variable:
            return item
    return {}


def evaluate_case(case_id: str, result: dict[str, Any]) -> dict[str, Any]:
    answer = str(result.get("answer") or "")
    trace = result.get("tool_results") or []

    def trace_ok(item: dict[str, Any]) -> bool:
        if item.get("ok") is False:
            return False
        payload = item.get("result")
        return not isinstance(payload, dict) or payload.get("ok") is not False

    checks: dict[str, bool] = {
        "sse_completed": bool(result.get("ok")) and "final" in (result.get("events") or []),
        "tool_execution_succeeded": bool(trace) and all(trace_ok(item) for item in trace),
    }
    derived: dict[str, Any] = {}

    if case_id in {"T1", "T2"}:
        payload = _tool_payload(result, "query_gl02_sensors")
        checks["expected_tool_selected"] = payload.get("tool") == "query_gl02_sensors"
        checks["authoritative_values_returned"] = bool(payload.get("success_count"))

    if case_id == "T1":
        payload = _tool_payload(result, "query_gl02_sensors")
        p_top = _sensor_item(payload, "P_top")
        dp_total = _sensor_item(payload, "DP_total")
        checks["two_requested_sensors_returned"] = bool(p_top.get("ok") and dp_total.get("ok"))
        checks["answer_contains_data_time"] = any(
            token in answer for token in ("数据时间", "时间", "2026-")
        )
        checks["model_reasoning_or_limit_statement"] = any(
            token in answer for token in ("不足", "只能", "推测", "判断", "需要")
        )
        derived["model_was_bypassed_by_deterministic_formatter"] = not checks[
            "model_reasoning_or_limit_statement"
        ]

    if case_id == "T2":
        payload = _tool_payload(result, "query_gl02_sensors")
        statistics = (_sensor_item(payload, "P_top").get("statistics") or {})
        avg = statistics.get("avg")
        stddev = statistics.get("stddev")
        minimum = statistics.get("min")
        maximum = statistics.get("max")
        value_range = None
        cv_percent = None
        if all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in (minimum, maximum)):
            value_range = float(maximum) - float(minimum)
        if (
            isinstance(avg, (int, float))
            and isinstance(stddev, (int, float))
            and math.isfinite(float(avg))
            and math.isfinite(float(stddev))
            and float(avg) != 0
        ):
            cv_percent = float(stddev) / float(avg) * 100.0
        derived.update({"range": value_range, "cv_percent": cv_percent})
        checks["statistics_complete_in_tool_result"] = all(
            statistics.get(key) is not None
            for key in ("count", "avg", "stddev", "min", "max", "first", "last", "delta", "slope_per_min")
        )
        checks["answer_contains_stddev"] = any(token in answer for token in ("标准差", "stddev"))
        checks["answer_contains_cv_formula"] = "CV" in answer and any(token in answer for token in ("÷", "/"))
        checks["answer_contains_independent_cv"] = (
            cv_percent is not None
            and any(f"{cv_percent:.{digits}f}" in answer for digits in (2, 3, 4, 6))
        )

    if case_id == "T3":
        payload = _tool_payload(result, "plot_gl02_analysis")
        correlation = (payload.get("derived") or {}).get("correlation") or {}
        pearson_r = correlation.get("pearson_r")
        aligned_count = correlation.get("aligned_count")
        derived.update({"pearson_r": pearson_r, "aligned_count": aligned_count})
        servers = {
            str(item.get("server_id") or "")
            for item in result.get("source_status") or []
            if item.get("server_id")
        }
        checks["two_mcp_services_used"] = {"imes-readonly", "gl02-data"}.issubset(servers)
        checks["correlation_tool_returned_evidence"] = (
            isinstance(pearson_r, (int, float)) and isinstance(aligned_count, int)
        )
        checks["answer_contains_pearson_r"] = (
            isinstance(pearson_r, (int, float))
            and any(f"{float(pearson_r):.{digits}f}" in answer for digits in (2, 3, 4, 6))
        )
        checks["answer_contains_aligned_count"] = aligned_count is not None and str(aligned_count) in answer
        checks["answer_avoids_causal_claim"] = not any(token in answer for token in ("导致", "造成", "因果关系"))

    answer_contract_keys = [key for key in checks if key.startswith("answer_") or key.startswith("model_")]
    answer_contract_passed = all(checks[key] for key in answer_contract_keys)
    tool_contract_keys = [key for key in checks if key not in answer_contract_keys]
    tool_contract_passed = all(checks[key] for key in tool_contract_keys)
    return {
        "case_id": case_id,
        "checks": checks,
        "derived": derived,
        "tool_contract_passed": tool_contract_passed,
        "answer_contract_passed": answer_contract_passed,
        "overall_passed": tool_contract_passed and answer_contract_passed,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://10.30.220.12:8093/api/qa/chat")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--case", choices=["all", *CASES], default="all")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    selected = list(CASES) if args.case == "all" else [args.case]
    if args.dry_run:
        print(json.dumps({key: {"name": CASES[key][0], "question": CASES[key][1]} for key in selected}, ensure_ascii=False, indent=2))
        return 0

    rows = []
    for case_id in selected:
        name, question = CASES[case_id]
        try:
            raw = run_once(args.url, question, args.timeout)
            evaluation = evaluate_case(case_id, raw)
            rows.append({"case_id": case_id, "name": name, "raw": raw, "evaluation": evaluation})
        except Exception as exc:  # one attempt only; never replay
            rows.append({"case_id": case_id, "name": name, "error": f"{type(exc).__name__}: {exc}"})

    report = {
        "schema": "bf.agent-tool-capability.mcp-sensor-reasoning.v1",
        "evaluation_id": "Q-MCP-SENSOR-REASONING-20260813",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "url": args.url,
        "retry_policy": "none",
        "request_count": len(selected),
        "rows": rows,
        "summary": {
            "executed": len(rows),
            "tool_contract_passed": sum(bool((row.get("evaluation") or {}).get("tool_contract_passed")) for row in rows),
            "answer_contract_passed": sum(bool((row.get("evaluation") or {}).get("answer_contract_passed")) for row in rows),
            "overall_passed": sum(bool((row.get("evaluation") or {}).get("overall_passed")) for row in rows),
        },
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["summary"]["overall_passed"] == len(selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())
