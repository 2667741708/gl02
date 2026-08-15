from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "evaluate_8093_mcp_sensor_reasoning",
    TOOLS / "evaluate_8093_mcp_sensor_reasoning.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def sensor_result(answer: str) -> dict:
    return {
        "ok": True,
        "events": ["start", "start", "tool_start", "tool_result", "delta", "final", "done"],
        "answer": answer,
        "tool_results": [
            {
                "tool": "query_gl02_sensors",
                "result": {
                    "ok": True,
                    "tool": "query_gl02_sensors",
                    "success_count": 2,
                    "items": [
                        {
                            "requested_variable": "P_top",
                            "ok": True,
                            "statistics": {
                                "count": 60,
                                "avg": 250.0,
                                "stddev": 1.0,
                                "min": 248.0,
                                "max": 252.0,
                                "first": {"ts": "2026-08-13T10:00:00", "value": 249.0},
                                "last": {"ts": "2026-08-13T11:00:00", "value": 251.0},
                                "delta": 2.0,
                                "slope_per_min": 0.02,
                            },
                        },
                        {
                            "requested_variable": "DP_total",
                            "ok": True,
                            "statistics": {"count": 60, "avg": 180.0},
                        },
                    ],
                },
            }
        ],
    }


def test_t2_separates_tool_success_from_incomplete_answer() -> None:
    result = MODULE.evaluate_case("T2", sensor_result("顶压均值 250，趋势上升"))
    assert result["tool_contract_passed"] is True
    assert result["answer_contract_passed"] is False
    assert result["derived"] == {"range": 4.0, "cv_percent": 0.4}


def test_t3_reads_full_source_status_result_for_correlation() -> None:
    result = MODULE.evaluate_case(
        "T3",
        {
            "ok": True,
            "events": ["final"],
            "answer": "Pearson r=-0.134，对齐样本 60；这不代表因果。",
            "tool_results": [{"tool": "a", "ok": True}, {"tool": "b", "ok": True}],
            "source_status": [
                {"server_id": "imes-readonly", "tool": "imes__get_current_previous_heat_si_summary"},
                {
                    "server_id": "gl02-data",
                    "tool": "plot_gl02_analysis",
                    "result_text": '{"derived":{"correlation":{"pearson_r":-0.134,"aligned_count":60}}}',
                },
            ],
        },
    )
    assert result["tool_contract_passed"] is True
    assert result["answer_contract_passed"] is True
    assert result["derived"]["aligned_count"] == 60


def test_dry_run_cases_are_stable() -> None:
    assert list(MODULE.CASES) == ["T1", "T2", "T3"]
    assert "CV=标准差÷均值×100%" in MODULE.CASES["T2"][1]
    assert "禁止把相关性说成因果" in MODULE.CASES["T3"][1]
