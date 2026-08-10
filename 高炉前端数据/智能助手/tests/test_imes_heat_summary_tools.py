from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PYLIBS = ROOT / ".tmp_pylibs"
if str(PYLIBS) not in sys.path:
    sys.path.insert(0, str(PYLIBS))


class _FakeFastMCP:
    def __init__(self, *args, **kwargs):
        self.registered = []

    def tool(self):
        def decorator(function):
            self.registered.append(function.__name__)
            return function

        return decorator

    def run(self, *args, **kwargs):
        return None


def _load_imes_module(monkeypatch):
    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = _FakeFastMCP
    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_module)
    path = ROOT / "高炉前端数据" / "智能助手" / "mcp" / "imes_relay_mcp_server.py"
    spec = importlib.util.spec_from_file_location("imes_relay_mcp_server_summary_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_previous_heat_si_summary_uses_official_meltno_and_all_valid_samples(monkeypatch):
    module = _load_imes_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "_query_recent_heat_context_rows",
        lambda anchor, furnace_id, limit=2: [
            {"meltno": "2#1002", "opentime": "2026-08-05T06:30:00", "closetime": None},
            {"meltno": "2#1001", "opentime": "2026-08-05T05:00:00", "closetime": "2026-08-05T06:00:00"},
        ],
    )
    monkeypatch.setattr(
        module,
        "_query_hot_metal_chemistry_rows",
        lambda heat_no: [
            {"batchno": "A", "si": "0.21", "takesampletime": "2026-08-05T05:20:00"},
            {"batchno": "B", "si": 0.31, "takesampletime": "2026-08-05T05:40:00"},
            {"batchno": "C", "si": None, "takesampletime": "2026-08-05T05:50:00"},
        ],
    )
    result = module.get_current_previous_heat_si_summary("2026-08-05T07:07:27", "2#")
    assert result["current_heat_no"] == "2#1002"
    assert result["previous_heat_no"] == "2#1001"
    assert result["sample_count"] == 2
    assert result["si_avg"] == 0.26
    assert result["si_min"] == 0.21
    assert result["si_max"] == 0.31
    assert result["account_profiles"] == {
        "heat_context": "operations",
        "chemistry": module.CHEMISTRY_ACCOUNT_PROFILE,
    }
    assert result["quality"]["official_meltno"] is True


def test_no_si_samples_is_missing_not_zero(monkeypatch):
    module = _load_imes_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "_query_recent_heat_context_rows",
        lambda anchor, furnace_id, limit=2: [{"meltno": "2#1002"}, {"meltno": "2#1001"}],
    )
    monkeypatch.setattr(module, "_query_hot_metal_chemistry_rows", lambda heat_no: [{"si": None}])
    result = module.get_current_previous_heat_si_summary("2026-08-05T07:07:27", "2")
    assert result["ok"] is True
    assert result["missing"] is True
    assert result["error_code"] == "NO_SI_SAMPLES"
    assert result["si_avg"] is None


def test_invalid_furnace_identifier_is_rejected(monkeypatch):
    module = _load_imes_module(monkeypatch)
    try:
        module._normalize_furnace_id("2#; DROP TABLE x")
    except ValueError as exc:
        assert "furnace_id" in str(exc)
    else:
        raise AssertionError("invalid furnace identifier was accepted")


def test_recent_heat_query_orders_by_official_time_before_active_status(monkeypatch):
    module = _load_imes_module(monkeypatch)
    calls = []

    class Cursor:
        description = [("meltno",), ("opentime",), ("closetime",)]

        def execute(self, query, params):
            calls.append((query, params))

        def fetchall(self):
            return [
                ("2#20260805-065", "2026-08-05T06:00:00", None),
                ("2#20240805-056", "2024-08-05T06:00:00", None),
            ]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(module, "connection", lambda profile="operations": Connection())
    rows = module._query_recent_heat_context_rows(
        datetime(2026, 8, 5, 7, 7, 27), "2#", limit=2
    )
    assert rows[0]["meltno"] == "2#20260805-065"
    assert calls and "ORDER BY COALESCE(opentime, workdate) DESC" in calls[0][0]
    assert calls[0][1] == ("2#%", datetime(2026, 8, 5, 7, 7, 27), 2)


def test_query_heat_chemistry_filters_components_and_builds_summary(monkeypatch):
    module = _load_imes_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "query_hot_metal_chemistry_by_heat",
        lambda heat_no, furnace_id="2#": {
            "ok": True,
            "resolved_heat_no": "2#20260805-065",
            "resolution_policy": "exact",
            "heat_time_window": {
                "start": "2026-08-05T04:00:00",
                "end": "2026-08-05T06:45:00",
            },
            "rows": [
                {
                    "heatno": "2#20260805-065",
                    "batchno": "B2",
                    "takesampletime": "2026-08-05T05:54:00",
                    "publishtime": "2026-08-05T06:10:00",
                    "judgetime": "2026-08-05T06:11:00",
                    "si": "0.36",
                    "mn": "0.22",
                },
                {
                    "heatno": "2#20260805-065",
                    "batchno": "B1",
                    "takesampletime": "2026-08-05T04:53:00",
                    "publishtime": "2026-08-05T05:05:00",
                    "judgetime": "2026-08-05T05:06:00",
                    "si": "0.38",
                    "mn": None,
                },
            ],
        },
    )
    result = module.query_heat_chemistry(
        "2#20260805-065", components=["硅", "Mn"]
    )
    assert result["ok"] is True
    assert result["tool_contract"] == "heat_chemistry.v1"
    assert result["components"] == ["si", "mn"]
    assert result["sample_count"] == 2
    assert result["summary"]["si"] == {
        "count": 2,
        "avg": 0.37,
        "min": 0.36,
        "max": 0.38,
        "latest": 0.36,
        "unit": "%",
        "missing": False,
    }
    assert result["summary"]["mn"]["count"] == 1
    assert result["data_time"] == "2026-08-05T06:11:00"
    assert result["source_service"] == "imes-readonly"


def test_query_heat_chemistry_rejects_unknown_component(monkeypatch):
    module = _load_imes_module(monkeypatch)
    try:
        module.query_heat_chemistry("065", components=["铁"])
    except ValueError as exc:
        assert "unsupported chemistry component" in str(exc)
    else:
        raise AssertionError("unknown component was accepted")


def test_query_heat_chemistry_is_registered_as_mcp_tool(monkeypatch):
    module = _load_imes_module(monkeypatch)
    assert "query_heat_chemistry" in module.mcp.registered



def test_current_heat_chemistry_returns_partial_available_samples(monkeypatch):
    module = _load_imes_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "get_current_heat_context",
        lambda as_of_time=None, furnace_id="2#": {
            "ok": True,
            "status": "active",
            "as_of_time": "2026-08-07T07:00:00",
            "current_heat_no": "2#20260807-081",
            "current_heat": {
                "opentime": "2026-08-07T05:10:00",
                "closetime": None,
            },
        },
    )
    monkeypatch.setattr(
        module,
        "query_heat_chemistry",
        lambda **kwargs: {
            "ok": True,
            "resolved_heat_no": "2#20260807-081",
            "components": ["si"],
            "summary": {
                "si": {
                    "count": 2,
                    "avg": 0.275,
                    "min": 0.26,
                    "max": 0.29,
                    "unit": "%",
                    "missing": False,
                }
            },
            "samples": [
                {
                    "sample_no": "S1",
                    "tank_no": "T01",
                    "sample_time": "2026-08-07T05:45:00",
                    "sample_time_type": "judge_time",
                    "components": {"si": 0.26},
                },
                {
                    "sample_no": "S2",
                    "tank_no": "T02",
                    "sample_time": "2026-08-07T06:35:00",
                    "sample_time_type": "publish_time",
                    "components": {"si": 0.29},
                },
            ],
            "missing": False,
        },
    )
    result = module.query_current_heat_chemistry(
        as_of_time="2026-08-07T07:00:00",
        components=["si"],
    )
    assert result["resolved_heat_no"] == "2#20260807-081"
    assert result["provisional"] is True
    assert result["partial_heat"] is True
    assert result["open_time"] == "2026-08-07T05:10:00"
    assert result["summary"]["si"]["avg"] == 0.275
    assert [item["tank_no"] for item in result["samples"]] == ["T01", "T02"]


def test_spoken_time_range_parses_yesterday_clock_window(monkeypatch):
    module = _load_imes_module(monkeypatch)
    result = module._parse_spoken_heat_time_range(
        "昨天上午4点到7点的炉次硅含量",
        "2026-08-07T10:00:00",
    )
    assert result["start"] == "2026-08-06T04:00:00"
    assert result["end"] == "2026-08-06T07:00:00"
    assert result["resolution_policy"] == "spoken_clock_range"


def test_time_range_query_returns_all_overlapping_heats_and_samples(monkeypatch):
    module = _load_imes_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "_query_heat_context_rows_near_range",
        lambda start, end, furnace_id, limit=24: [
            {
                "meltno": "2#20260806-079",
                "opentime": "2026-08-06T04:30:00",
                "closetime": "2026-08-06T05:30:00",
            },
            {
                "meltno": "2#20260806-080",
                "opentime": "2026-08-06T06:00:00",
                "closetime": "2026-08-06T07:20:00",
            },
        ],
    )

    def chemistry(**kwargs):
        heat_no = kwargs["heat_reference"]
        value = 0.31 if heat_no.endswith("079") else 0.28
        return {
            "ok": True,
            "resolved_heat_no": heat_no,
            "components": ["si"],
            "summary": {
                "si": {
                    "count": 1,
                    "avg": value,
                    "min": value,
                    "max": value,
                    "missing": False,
                }
            },
            "samples": [
                {
                    "sample_no": heat_no[-3:] + "-1",
                    "tank_no": "T-" + heat_no[-3:],
                    "sample_time": "2026-08-06T05:00:00",
                    "sample_time_type": "judge_time",
                    "components": {"si": value},
                }
            ],
            "missing": False,
        }

    monkeypatch.setattr(module, "query_heat_chemistry", chemistry)
    result = module.query_heat_chemistry_by_time_range(
        "2026年8月6日4点到7点",
        components=["si"],
        as_of_time="2026-08-07T10:00:00",
    )
    assert result["matched_heat_count"] == 2
    assert result["primary_heat_no"] in {
        "2#20260806-079",
        "2#20260806-080",
    }
    assert {item["heat_no"] for item in result["heats"]} == {
        "2#20260806-079",
        "2#20260806-080",
    }
    assert all(item["chemistry"]["samples"] for item in result["heats"])


def test_time_range_ignores_workdate_only_planned_heat(monkeypatch):
    module = _load_imes_module(monkeypatch)
    ranked = module._rank_heat_for_time_range(
        {
            "meltno": "2#20260807-098",
            "workdate": "2026-08-07T00:00:00",
            "opentime": None,
            "closetime": None,
        },
        module._normalize_as_of_time("2026-08-07T07:00:00"),
        module._normalize_as_of_time("2026-08-07T11:00:00"),
        module._normalize_as_of_time("2026-08-07T11:20:00"),
    )
    assert ranked is None


def test_time_range_rebases_known_mes_time_anomaly_with_dual_date_anchor(monkeypatch):
    module = _load_imes_module(monkeypatch)
    ranked = module._rank_heat_for_time_range(
        {
            "meltno": "2#20260806-090",
            "workdate": "2026-08-06T00:00:00",
            "opentime": "2026-08-07T23:33:00",
            "closetime": "2026-08-07T00:30:00",
        },
        module._normalize_as_of_time("2026-08-06T23:00:00"),
        module._normalize_as_of_time("2026-08-07T01:00:00"),
        module._normalize_as_of_time("2026-08-07T11:20:00"),
    )
    assert ranked is not None
    assert ranked["open_time"].isoformat() == "2026-08-06T23:33:00"
    assert ranked["close_time"].isoformat() == "2026-08-07T00:30:00"
    assert ranked["time_status"] == "time_anomaly_repaired"
    assert "opentime_date_rebased_to_workdate" in ranked["time_repair_reasons"]
    assert "closetime_rollover_next_day" in ranked["time_repair_reasons"]


def test_current_and_time_range_tools_are_registered(monkeypatch):
    module = _load_imes_module(monkeypatch)
    assert "query_current_heat_chemistry" in module.mcp.registered
    assert "query_heat_chemistry_by_time_range" in module.mcp.registered
