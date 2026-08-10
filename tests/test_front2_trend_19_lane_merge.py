from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "高炉前端数据" / "front2" / "frontend_dashboard_front2.server.html"
EXPECTED = [
    "P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "T_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "Q_blast",
    "P_blast_cold", "P_blast", "T_blast", "PI", "DP_total", "DP_upper",
    "DP_lower", "GasUtil",
]


def source() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_exact_19_target_contract() -> None:
    text = source()
    match = re.search(r"const TREND_PREDICT_IDS=(\[[^;]+\]);", text)
    assert match
    assert ast.literal_eval(match.group(1)) == EXPECTED


def test_single_foreman_lane_panel_contract() -> None:
    text = source()
    assert "REQ-TREND-19-LANE-MERGE-20260807" in text
    assert "function trendLaneOption" in text
    assert "trendLaneStats" in text
    assert "quantileSorted(values,.1)" in text
    assert "quantileSorted(values,.9)" in text
    override = text.split("TrendTab=function", 1)[1].split("function firstValidHistoryTime", 1)[0]
    assert override.count('className="trend-chart-stack trend-lane-single"') == 1
    assert override.count('title="19个核心变量趋势与预测"') == 1
    assert "chartSets.map" not in override
    assert "trendLaneOption(buf,predictIds" in override


def test_history_forecast_share_lane_transform_and_raw_tooltip() -> None:
    text = source()
    block = text.split("function trendLaneOption", 1)[1].split("TrendTab=function", 1)[0]
    assert "project(id,raw)" in block
    assert "'历史'" in block
    assert "'预测'" in block
    assert "connectNulls:false" in block
    assert "value[2]" in block
    assert "type:'dashed'" in block
    assert "markArea" in block and "预测区" in block
    assert "dataZoom:[{type:'inside',filterMode:'none',zoomOnMouseWheel:true,moveOnMouseMove:true}],series}}" in block


def test_manual_and_automatic_requests_use_all_targets() -> None:
    text = source()
    assert text.count("target_ids:TREND_PREDICT_IDS") == 1
    assert text.count("target_ids:(ids||[]).filter(id=>TREND_PREDICT_IDS.includes(id))") == 1
    for target in EXPECTED:
        assert f"{target}_mean:'{target}'" in text or target == "T_top"
