from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "evaluate_mcp_extended_production.py"
SPEC = importlib.util.spec_from_file_location("evaluate_mcp_extended_production", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_matrix_has_fourteen_variables_and_forty_two_cases() -> None:
    spec, cases = MODULE.load_cases(ROOT / "PT" / "智能体工具能力扩展生产回归.v1.json")
    assert len(spec["variables"]) == 14
    assert len(cases) == 42
    assert len({case["case_id"] for case in cases}) == 42


def test_spoken_matrix_has_no_canonical_id_in_user_prompts() -> None:
    spec, cases = MODULE.load_cases(ROOT / "PT" / "智能体工具能力口语化生产回归.v1.json")
    assert spec["prompt_policy"] == "chinese_semantics_only_allow_position_letters_A_to_H"
    assert len(cases) == 42
    assert MODULE.validate_spoken_prompt_policy(spec, cases, ROOT) == []
    prompts = "\n".join(case["prompt"] for case in cases)
    for spoken_name in ("炉顶压力", "风温", "南尺", "北尺", "实际喷煤量", "鼓风富氧比例", "氧气流量"):
        assert spoken_name in prompts


def test_spoken_policy_allows_position_letters_but_rejects_internal_ids() -> None:
    known = {"P_top", "T_top_A", "DP_total", "L", "PI"}
    assert MODULE.spoken_prompt_technical_ids("比较顶温 A 点和 B 点", known) == []
    assert MODULE.spoken_prompt_technical_ids("比较炉体 7 层 A 到 H 各点温度", known) == []
    assert MODULE.spoken_prompt_technical_ids("查询 P_top 和 T_top_A", known) == ["P_top", "T_top_A"]
    assert MODULE.spoken_prompt_technical_ids("查询 DP_total、L 和 PI", known) == ["DP_total", "L", "PI"]
    assert MODULE.spoken_prompt_technical_ids("查询 P_top_gas_X", known) == ["P_top_gas_X"]


def test_latest_contract_scores_one_exact_sensor_call() -> None:
    case = {"object_id": "P_top", "query_type": "latest", "case_id": "x"}
    raw = {
        "ok": True,
        "events": ["final"],
        "answer": "顶压（P_top）258 kPa；数据时间：2026-08-14；质量：Good；来源：readonly。",
        "tool_starts": [{"tool": "query_gl02_sensors", "arguments": {"variables": ["P_top"], "query_type": "latest"}}],
        "tool_results": [{"tool": "query_gl02_sensors", "result": {"ok": True, "items": [{"ok": True}]}}],
    }
    assert all(MODULE.score_case(case, raw).values())


def test_statistics_contract_rejects_missing_evidence_fields() -> None:
    case = {"object_id": "PI", "query_type": "statistics", "case_id": "x"}
    raw = {
        "ok": True,
        "events": ["final"],
        "answer": "PI 均值 1.2，无量纲；时间范围：最近1小时；来源：readonly。",
        "tool_starts": [{"tool": "query_gl02_sensors", "arguments": {"variables": ["PI"], "query_type": "statistics"}}],
        "tool_results": [{"tool": "query_gl02_sensors", "result": {"ok": True, "items": [{"ok": True, "statistics": {"avg": 1.2, "stddev": 0.1}}]}}],
    }
    checks = MODULE.score_case(case, raw)
    assert checks["statistics_complete"] is False
