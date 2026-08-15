from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = ROOT / "高炉前端数据" / "智能助手" / "mcp"
BACKEND_DIR = ROOT / "高炉前端数据" / "智能助手" / "backend"
for path in (MCP_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _catalog():
    path = ROOT / "数据库同步和存取" / "config" / "点位语义目录.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_authoritative_points_have_spoken_aliases_and_expressions():
    catalog = _catalog()
    assert catalog["schema_version"] == "semantic_point_catalog.v1"
    assert catalog["object_count"] == 153
    assert catalog["physical_sensor_count"] == 151
    assert catalog["derived_metric_count"] == 2
    assert len(catalog["objects"]) == 153
    assert len({item["object_id"] for item in catalog["objects"]}) == 153
    assert all(len(item["semantic_aliases"]) >= 2 for item in catalog["objects"])
    assert all(len(item["spoken_expressions"]) == 4 for item in catalog["objects"])
    assert {item["object_id"] for item in catalog["objects"] if item["object_kind"] == "derived_metric"} == {
        "T_top",
        "PCI_current_hour",
    }


def test_runtime_resolves_every_generated_alias_to_exact_object():
    mcp = importlib.import_module("bf_data_mcp_server")
    for item in _catalog()["objects"]:
        assert any(variable["variable_name"] == item["object_id"] for variable in mcp.VARIABLES)
        for alias in item["semantic_aliases"]:
            assert mcp.resolve_variable(alias)["variable_name"] == item["object_id"], (item["object_id"], alias)


def test_each_primary_spoken_expression_routes_without_wrong_extra_point():
    proxy = importlib.import_module("ollama_proxy_server")
    for item in _catalog()["objects"]:
        actual = proxy.qa_mcp_variables(item["spoken_expressions"][0])
        assert actual == [item["object_id"]], (item["object_id"], actual)


def test_representative_multi_variable_comparisons_route_all_requested_points():
    proxy = importlib.import_module("ollama_proxy_server")
    cases = {
        "比较顶压A、顶压B、顶压C、顶压D当前值并计算最大最小差": [f"P_top_{p}" for p in "ABCD"],
        "比较顶温A、顶温B、顶温C、顶温D的平均值": [f"T_top_{p}" for p in "ABCD"],
        "对比7层A点、B点、C点炉体温度": [f"T_body_L7_{p}" for p in "ABC"],
        "比较软水流量和高压水流量": ["Q_soft_water", "Q_high_pressure_water"],
        "比较热风压力、冷风压力和全炉压差": ["P_blast", "P_blast_cold", "DP_total"],
        "比较炉顶一氧化碳、二氧化碳和氢气": ["CO_top", "CO2_top", "H2_top"],
    }
    for question, expected in cases.items():
        assert proxy.qa_mcp_variables(question) == expected


def test_unknown_machine_and_spoken_ids_fail_closed():
    mcp = importlib.import_module("bf_data_mcp_server")
    for value in ("DP_totl", "完全不存在的虚构点位XYZ"):
        try:
            mcp.resolve_variable(value)
        except ValueError as exc:
            assert "未找到变量" in str(exc)
        else:
            raise AssertionError(f"unknown point unexpectedly resolved: {value}")
