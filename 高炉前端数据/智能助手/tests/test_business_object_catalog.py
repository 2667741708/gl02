from __future__ import annotations

import json
import sys
from pathlib import Path


MCP_DIR = Path(__file__).resolve().parents[1] / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

import business_object_catalog as catalog_module  # noqa: E402
import bf_data_mcp_server as mcp_server  # noqa: E402


REQUIRED_CATALOG_FILES = {
    "catalog_manifest.json",
    "business_object.schema.json",
    "sensors.json",
    "heat_analysis.json",
    "calculation_tools.json",
    "chart_capabilities.json",
    "knowledge_assets.json",
}


def test_all_unified_catalog_files_exist_and_are_valid_json():
    actual = {path.name for path in catalog_module.CATALOG_DIR.glob("*.json")}
    assert REQUIRED_CATALOG_FILES <= actual
    for filename in REQUIRED_CATALOG_FILES:
        payload = json.loads((catalog_module.CATALOG_DIR / filename).read_text(encoding="utf-8"))
        assert isinstance(payload, dict)


def test_catalog_covers_all_planned_business_object_types():
    expected = {
        "sensor",
        "heat",
        "hot_metal_analysis",
        "slag_analysis",
        "feed_chemistry",
        "report",
        "qa_history",
        "calculation",
        "chart",
    }
    assert expected <= set(mcp_server.BUSINESS_OBJECT_CATALOG["counts_by_type"])


def test_every_catalog_object_obeys_unified_contract():
    objects = mcp_server.BUSINESS_OBJECT_CATALOG["objects"]
    assert objects
    for item in objects:
        assert all(field in item for field in catalog_module.REQUIRED_FIELDS)
        assert item["object_id"]
        assert item["display_name"]
        assert isinstance(item["aliases"], list)
        assert isinstance(item["capabilities"], list) and item["capabilities"]
        assert item["status"] in catalog_module.ALLOWED_STATUS
        assert item["executor"]["service"]
        assert isinstance(item["executor"]["tools"], list)


def test_all_18_static_pressure_points_are_in_sensor_catalog():
    extension = json.loads(
        (MCP_DIR / "gl02_static_pressure_points.json").read_text(encoding="utf-8")
    )["variables"]
    static_ids = {item["variable_name"] for item in extension}
    catalog_ids = {
        item["object_id"]
        for item in mcp_server.BUSINESS_OBJECT_CATALOG["objects"]
        if item["object_type"] == "sensor"
    }
    assert len(static_ids) == 18
    assert static_ids <= catalog_ids


def test_catalog_search_resolves_sensor_heat_slag_feed_report_and_chart():
    cases = {
        "炉顶压力": "P_top",
        "铁水硅含量": "hot_metal_chemistry",
        "炉渣成分": "blast_furnace_slag_chemistry",
        "进料化学成分": "sinter_feed_chemistry",
        "最近日报": "production_report",
        "相关散点图": "correlation_chart",
    }
    for query, expected_id in cases.items():
        result = mcp_server.search_business_objects(query)
        assert result["ok"] is True
        assert expected_id in {item["object_id"] for item in result["matches"]}, query


def test_get_and_list_business_object_tools_return_contract():
    top = mcp_server.get_business_object("P_top")
    chemistry = mcp_server.get_business_object("hot_metal_chemistry")
    charts = mcp_server.list_business_objects(object_type="chart")
    assert top["ok"] is True
    assert top["object"]["capabilities"] == ["latest", "history", "statistics", "plot", "correlation"]
    assert chemistry["ok"] is True
    assert "lookup_by_heat" in chemistry["object"]["capabilities"]
    assert charts["ok"] is True
    assert charts["count"] >= 5


def test_unknown_business_object_returns_structured_error():
    result = mcp_server.get_business_object("not_a_real_object")
    assert result["ok"] is False
    assert result["error"] == "BUSINESS_OBJECT_NOT_FOUND"


def test_core_fallback_has_top_pressure_and_total_pressure_drop():
    assert mcp_server.resolve_variable("P_top")["short_name"] == "SIO_GL02_LD_T0034"
    assert mcp_server.resolve_variable("DP_total")["short_name"] == "SIO_GL02_BT_T0132"


def test_top_pressure_abcd_uses_canonical_names_with_legacy_aliases():
    for offset, position in enumerate("ABCD", start=67):
        canonical = mcp_server.resolve_variable(f"P_top_{position}")
        legacy = mcp_server.resolve_variable(f"P_top_gas_{position}")
        spoken = mcp_server.resolve_variable(f"{position}点顶压")
        assert canonical["variable_name"] == f"P_top_{position}"
        assert canonical["short_name"] == f"SIO_GL02_LD_T{offset:04d}"
        assert legacy["variable_name"] == f"P_top_{position}"
        assert spoken["variable_name"] == f"P_top_{position}"


def test_unknown_canonical_sensor_id_is_never_fuzzy_mapped():
    try:
        mcp_server.resolve_variable("DP_totl")
    except ValueError as exc:
        assert "未找到变量" in str(exc)
    else:
        raise AssertionError("unknown canonical identifier must not resolve to another sensor")
