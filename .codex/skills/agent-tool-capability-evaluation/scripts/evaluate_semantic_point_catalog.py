"""Evaluate complete spoken aliases and representative multi-variable plans."""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * ratio))]


def load_modules(root: Path):
    mcp_dir = root / "高炉前端数据" / "智能助手" / "mcp"
    backend_dir = root / "高炉前端数据" / "智能助手" / "backend"
    for path in (mcp_dir, backend_dir):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return importlib.import_module("bf_data_mcp_server"), importlib.import_module("ollama_proxy_server")


def evaluate(root: Path, catalog_path: Path) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    mcp, proxy = load_modules(root)
    ids = {str(item.get("variable_name")) for item in mcp.VARIABLES}
    failures: list[dict[str, Any]] = []
    latencies: list[float] = []
    alias_total = 0
    alias_passed = 0
    spoken_total = 0
    spoken_passed = 0

    for item in catalog.get("objects") or []:
        object_id = item["object_id"]
        if object_id not in ids:
            failures.append({"kind": "catalog_coverage", "object_id": object_id})
            continue
        for alias in item.get("semantic_aliases") or []:
            alias_total += 1
            started = time.perf_counter()
            try:
                resolved = mcp.resolve_variable(alias).get("variable_name")
            except Exception as exc:  # noqa: BLE001
                resolved = f"ERROR:{type(exc).__name__}:{exc}"
            latencies.append((time.perf_counter() - started) * 1000)
            if resolved == object_id:
                alias_passed += 1
            else:
                failures.append({"kind": "alias_top1", "object_id": object_id, "input": alias, "actual": resolved})
        expression = (item.get("spoken_expressions") or [""])[0]
        spoken_total += 1
        actual = proxy.qa_mcp_variables(expression)
        if object_id in actual:
            spoken_passed += 1
        else:
            failures.append({"kind": "spoken_route", "object_id": object_id, "input": expression, "actual": actual})

    composite_cases = [
        {"question": "比较顶压A、顶压B、顶压C、顶压D当前值并计算最大最小差", "expected": [f"P_top_{p}" for p in "ABCD"]},
        {"question": "比较顶温A、顶温B、顶温C、顶温D的平均值", "expected": [f"T_top_{p}" for p in "ABCD"]},
        {"question": "对比7层A点、B点、C点炉体温度", "expected": [f"T_body_L7_{p}" for p in "ABC"]},
        {"question": "比较软水流量和高压水流量", "expected": ["Q_soft_water", "Q_high_pressure_water"]},
        {"question": "比较热风压力、冷风压力和全炉压差", "expected": ["P_blast", "P_blast_cold", "DP_total"]},
        {"question": "比较炉顶一氧化碳、二氧化碳和氢气", "expected": ["CO_top", "CO2_top", "H2_top"]},
    ]
    composite_passed = 0
    composite_results = []
    for case in composite_cases:
        actual = proxy.qa_mcp_variables(case["question"])
        ok = actual == case["expected"]
        composite_passed += int(ok)
        composite_results.append({**case, "actual": actual, "ok": ok})
        if not ok:
            failures.append({"kind": "composite_route", **composite_results[-1]})

    unknown_rejected = False
    try:
        mcp.resolve_variable("完全不存在的虚构点位XYZ")
    except ValueError:
        unknown_rejected = True
    if not unknown_rejected:
        failures.append({"kind": "unknown_rejection", "input": "完全不存在的虚构点位XYZ"})

    coverage_passed = sum(1 for item in catalog.get("objects") or [] if item["object_id"] in ids)
    return {
        "schema": "agent_tool_capability.point_catalog.v1",
        "catalog_version": catalog.get("catalog_version"),
        "catalog_hash": catalog.get("catalog_hash"),
        "dimensions": {
            "semantic_resolution": {
                "catalog_coverage": {"passed": coverage_passed, "total": catalog.get("object_count")},
                "alias_top1": {"passed": alias_passed, "total": alias_total},
                "spoken_route": {"passed": spoken_passed, "total": spoken_total},
                "unknown_rejected": unknown_rejected,
                "p95_ms": percentile(latencies, 0.95),
            },
            "tool_selection_and_arguments": {
                "composite_route": {"passed": composite_passed, "total": len(composite_cases)},
                "cases": composite_results,
            },
            "executable_calls": {"status": "not_tested", "reason": "offline catalog evaluation does not call production MCP data sources"},
            "multi_turn_composite": {"status": "route_contract_tested", "live_cross_mcp_evidence": "Q-8093-CROSS-MCP-COMPUTATION-20260813"},
            "answer_grounding": {"status": "covered_by_live_cross_mcp_evidence"},
            "failure_safety": {"unknown_id_fail_closed": unknown_rejected},
            "performance_cost": {"exact_alias_p95_ms": percentile(latencies, 0.95)},
            "concurrency_stability": {"status": "covered_by_tests/test_qa_mcp_parallel_planning.py"},
            "security_audit": {"status": "not_tested", "reason": "no authentication or write tool exercised"},
        },
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--catalog", type=Path, default=Path("数据库同步和存取/config/点位语义目录.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    catalog = args.catalog if args.catalog.is_absolute() else root / args.catalog
    result = evaluate(root, catalog)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
