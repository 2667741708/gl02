# -*- coding: utf-8 -*-
"""Build an 8094 trend-only payload from the live-page snapshot.

The live 8094 page contains production features that are intentionally absent
from the front2 source.  This builder therefore ports only the validated trend
override and Chronos contract changes instead of replacing the whole page.
"""

from __future__ import annotations

import re
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "高炉前端数据" / "front2" / "frontend_dashboard_front2.server.html"
BEFORE = ROOT / "logs" / "deployment" / "trend19_8094_20260807" / "remote_before.html"
OUTPUT = ROOT / "logs" / "deployment" / "trend19_8094_20260807" / "frontend_dashboard_v3.8094_preview.server.html"

TARGET_IDS = [
    "P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "T_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "Q_blast",
    "P_blast_cold", "P_blast", "T_blast", "PI", "DP_total", "DP_upper",
    "DP_lower", "GasUtil",
]


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return updated


def extract_lane_override(source: str) -> str:
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if "REQ-TREND-19-LANE-MERGE-20260807" in line)
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("TrendTab=function"))
    block = "\n".join(lines[start : end + 1])
    required = ("trendLaneStats", "trendLaneOption", "trend-19-lane-merge-style", "19个核心变量趋势与预测")
    missing = [marker for marker in required if marker not in block]
    if missing:
        raise RuntimeError(f"validated lane block is incomplete: {missing}")
    return block


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, default=BEFORE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    source = SOURCE.read_text(encoding="utf-8")
    baseline = args.before.read_text(encoding="utf-8")
    live = baseline
    if "REQ-TREND-19-LANE-MERGE-20260807" in live:
        raise RuntimeError("live snapshot is already patched")

    ids_literal = "[" + ",".join(repr(item) for item in TARGET_IDS) + "]"
    declaration = (
        f"    const TREND_PREDICT_IDS={ids_literal};\n"
        "    function sanitizeTrendForecast(id,values,history){if(!Array.isArray(values))return [];"
        "const forecast=values.map(Number).filter(Number.isFinite),recent=(history||[]).slice(-30).map(Number).filter(Number.isFinite);"
        "if(forecast.length&&recent.some(value=>Math.abs(value)>1e-6)&&forecast.every(value=>Math.abs(value)<=1e-9))return [];"
        "return values;}\n"
    )
    live = replace_once(live, r"(?=    function trendRows\()", declaration, "target declaration anchor")

    lane_override = extract_lane_override(source)
    live = replace_once(
        live,
        r"(?=\s*function QaTabLegacy\()",
        lane_override + "\n",
        "trend override anchor",
    )

    mapping = (
        "chronosMap = { P_top_mean: 'P_top', P_top_gas_A_mean: 'P_top_gas_A', "
        "P_top_gas_B_mean: 'P_top_gas_B', P_top_gas_C_mean: 'P_top_gas_C', "
        "P_top_gas_D_mean: 'P_top_gas_D', T_top_selected_mean: 'T_top', "
        "T_top_mean: 'T_top', T_top_A_mean: 'T_top_A', T_top_B_mean: 'T_top_B', "
        "T_top_C_mean: 'T_top_C', T_top_D_mean: 'T_top_D', Q_blast_mean: 'Q_blast', "
        "P_blast_cold_mean: 'P_blast_cold', P_blast_mean: 'P_blast', "
        "T_blast_mean: 'T_blast', PI_mean: 'PI', DP_total_mean: 'DP_total', "
        "DP_upper_mean: 'DP_upper', DP_lower_mean: 'DP_lower', GasUtil_mean: 'GasUtil', "
        "PCI_mean: 'PCI_rate' }, normId = id => chronosMap[id] || String(id || '').replace(/_mean$/, '');"
    )
    live = replace_once(
        live,
        r"chronosMap = \{.*?\}, normId = id => chronosMap\[id\] \|\| id;",
        mapping,
        "Chronos response map",
    )
    live = replace_once(
        live,
        r"bufRef\.current\[`\$\{id\}__forecast`\]\s*=\s*arr",
        "bufRef.current[`${id}__forecast`] = sanitizeTrendForecast(id, arr, bufRef.current[id])",
        "prediction-array zero-collapse guard",
    )
    live = replace_once(
        live,
        r"target_ids: \['PI', 'DP_total', 'DP_lower', 'DP_upper', 'GasUtil', 'T_top', 'T_top_A', 'T_top_B', 'T_top_C', 'T_top_D'\]",
        "target_ids: TREND_PREDICT_IDS",
        "automatic prediction target list",
    )
    live = replace_once(
        live,
        r"target_ids: \(ids \|\| \[\]\)\.filter\(id => \['PI', 'DP_total', 'DP_lower', 'DP_upper', 'GasUtil', 'T_top', 'T_top_A', 'T_top_B', 'T_top_C', 'T_top_D'\]\.includes\(id\)\)",
        "target_ids: (ids || []).filter(id => TREND_PREDICT_IDS.includes(id))",
        "manual prediction target filter",
    )

    for marker in (
        "REQ-TREND-19-LANE-MERGE-20260807",
        "19个核心变量趋势与预测",
        "P_top_gas_D_mean: 'P_top_gas_D'",
        "P_blast_cold_mean: 'P_blast_cold'",
        "target_ids: TREND_PREDICT_IDS",
        "TREND_PREDICT_IDS.includes(id)",
        "sanitizeTrendForecast(id, arr, bufRef.current[id])",
    ):
        if marker not in live:
            raise RuntimeError(f"payload marker is missing: {marker}")
    for marker in ("OPS-8094-MULTI-CONDITION-REVIEW-20260805", "BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2"):
        if marker in baseline and marker not in live:
            raise RuntimeError(f"existing live marker was lost: {marker}")
    if live.count("REQ-TREND-19-LANE-MERGE-20260807") != 1:
        raise RuntimeError("trend requirement marker must be unique")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(live, encoding="utf-8", newline="\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
