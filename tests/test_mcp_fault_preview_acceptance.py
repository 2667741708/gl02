from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools" / "mcp_fault_preview_acceptance.py"
SPEC = importlib.util.spec_from_file_location("mcp_fault_preview_acceptance", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_four_fault_scenarios_are_explicit_and_production_safe() -> None:
    assert set(MODULE.SCENARIOS) == {"GOLD-009", "GOLD-010", "GOLD-011", "GOLD-014"}
    assert MODULE.SCENARIOS["GOLD-009"]["name"] == "timeout"
    assert MODULE.SCENARIOS["GOLD-010"]["name"] == "partial_failure"
    assert MODULE.SCENARIOS["GOLD-011"]["name"] == "all_tools_failed"
    assert MODULE.SCENARIOS["GOLD-014"]["name"] == "tool_result_injection"


def test_scenario_requires_explicit_case_id() -> None:
    case_id, scenario = MODULE.scenario_for("[GOLD-011] test")
    assert case_id == "GOLD-011"
    assert scenario["name"] == "all_tools_failed"


def test_answer_contract_accepts_semantically_equivalent_safe_wording() -> None:
    answer = "实时工具超时，未能获取当前数值。实时数据库未核实。"
    assert all(MODULE.answer_contract_checks("GOLD-009", answer).values())
