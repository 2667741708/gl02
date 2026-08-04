#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Verify that foreman-concerned GL02 variables are wired into the V4 frontend.

Requirement: REQ-20260516-FOREMAN-CORE-VARS
Docs: docs/requirements_traceability.md#req-20260516-foreman-core-vars
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_HTML = PROJECT_ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
WS_BRIDGE = PROJECT_ROOT / "自动诊断服务" / "local_pg_ws_bridge.py"
MCP_SERVER = PROJECT_ROOT / "高炉前端数据" / "智能助手" / "mcp" / "bf_data_mcp_server.py"

EXPECTED_CORE_IDS = [
    "DP_total",
    "DP_upper",
    "DP_lower",
    "PI",
    "P_top",
    "P_blast_cold",
    "P_blast",
    "T_blast",
    "Q_blast",
    "GasUtil",
    "T_top",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
    "L",
    "L_south",
    "L_north",
    "PCI_rate",
    "PCI_set",
    "Q_O2",
    "O2_rate",
    "TFT",
    "P_static_20m35",
    "P_static_23m49",
    "P_static_28m98",
    "T_throat_A",
    "T_throat_B",
    "T_throat_C",
    "T_throat_D",
    "T_taphole_1",
    "T_taphole_2",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_js_array_assignment(source: str, name: str) -> list[str]:
    match = re.search(rf"const\s+{re.escape(name)}\s*=\s*(\[[^\]]*\])", source)
    if not match:
        raise AssertionError(f"Missing JS array: {name}")
    return list(ast.literal_eval(match.group(1)))


def parse_python_list_assignment(source: str, name: str) -> list[str]:
    match = re.search(rf"{re.escape(name)}\s*=\s*(\[[\s\S]*?\n\])", source)
    if not match:
        raise AssertionError(f"Missing Python list: {name}")
    return list(ast.literal_eval(match.group(1)))


def missing(expected: list[str], actual: list[str] | set[str]) -> list[str]:
    actual_set = set(actual)
    return [item for item in expected if item not in actual_set]


def run() -> dict[str, Any]:
    html = read_text(FRONTEND_HTML)
    bridge = read_text(WS_BRIDGE)
    mcp = read_text(MCP_SERVER)

    frontend_core = parse_js_array_assignment(html, "FOREMAN_CORE_IDS")
    bridge_variables = parse_python_list_assignment(bridge, "FRONTEND_VARIABLES")

    html_missing = missing(EXPECTED_CORE_IDS, frontend_core)
    bridge_missing = missing(EXPECTED_CORE_IDS, bridge_variables)
    label_checks = {
        "富氧流量": "富氧流量" in html,
        "富氧率": "富氧率" in html,
        "理论燃烧温度": "理论燃烧温度" in html,
        "炉喉温度": "炉喉温度" in html,
        "三层静压力变量": all(item in html for item in ["P_static_20m35", "P_static_23m49", "P_static_28m98"]),
        "核心诊断变量": "核心诊断变量" in html,
        "无重点趋势切换": "重点趋势" not in html and "TREND_FOCUS_IDS" not in html,
    }
    mcp_checks = {
        "query_gl02_feature_statistics": "def query_gl02_feature_statistics" in mcp,
        "stddev": "stddev" in mcp,
        "z60": "z60" in mcp,
        "daily_baselines": "daily_baselines" in mcp,
    }

    failures = []
    if html_missing:
        failures.append({"surface": "frontend_core", "missing": html_missing})
    if bridge_missing:
        failures.append({"surface": "ws_bridge", "missing": bridge_missing})
    for name, ok in label_checks.items():
        if not ok:
            failures.append({"surface": "frontend_label", "missing": [name]})
    for name, ok in mcp_checks.items():
        if not ok:
            failures.append({"surface": "mcp_feature_api", "missing": [name]})

    return {
        "ok": not failures,
        "expected_core_count": len(EXPECTED_CORE_IDS),
        "frontend_core_count": len(frontend_core),
        "ws_bridge_count": len(bridge_variables),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify foreman core diagnostic variable frontend wiring.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.json else None))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
