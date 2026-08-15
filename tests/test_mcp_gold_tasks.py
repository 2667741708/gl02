from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex" / "skills" / "agent-tool-capability-evaluation" / "scripts" / "evaluate_mcp_gold_tasks.py"
SPEC = importlib.util.spec_from_file_location("evaluate_mcp_gold_tasks", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_canonical_catalog_has_fourteen_valid_cases_and_required_categories() -> None:
    path = ROOT / "PT" / "智能体工具能力金标任务清单.v1.json"
    payload = MODULE.load_catalog(path)
    assert MODULE.validate_catalog(payload) == []
    assert len(payload["cases"]) == 14
    assert MODULE.REQUIRED_CATEGORIES.issubset({case["category"] for case in payload["cases"]})


def test_mocked_contracts_cover_failure_safety_and_cv_oracle() -> None:
    payload = MODULE.load_catalog(ROOT / "PT" / "智能体工具能力金标任务清单.v1.json")
    results = {case["case_id"]: MODULE.mocked_result(case, 1) for case in payload["cases"]}
    assert all(row["status"] == "passed" for row in results.values())
    assert results["GOLD-009"]["checks"]["single_no_tool_fallback"] is True
    assert results["GOLD-011"]["checks"]["automatic_retries_zero"] is True
    assert results["GOLD-012"]["checks"]["no_write"] is True
    assert results["GOLD-013"]["checks"]["cv_recomputed_within_tolerance"] is True


def test_markdown_view_records_current_json_hash() -> None:
    path = ROOT / "PT" / "智能体工具能力金标任务清单.v1.json"
    markdown = MODULE.catalog_markdown(path, MODULE.load_catalog(path))
    import hashlib
    assert hashlib.sha256(path.read_bytes()).hexdigest() in markdown
    assert markdown.count("| `GOLD-") == 14


def test_live_contract_checks_tools_arguments_and_answer_tokens() -> None:
    case = {
        "expected_calls": [{"server_id": "gl02-data", "tool": "query_gl02_sensors", "arguments": {"variables": ["P_top"], "query_type": "latest"}}],
        "answer_contract": {"must_include": ["P_top", "来源"], "must_not_include": ["实时数据库未核实"]},
    }
    raw = {
        "ok": True, "events": ["start", "final"], "answer": "P_top 255kPa；来源：gl02-data。",
        "tool_starts": [{"tool": "query_gl02_sensors", "arguments": {"variables": ["P_top"], "query_type": "latest"}}],
        "source_status": [{"server_id": "gl02-data", "tool": "query_gl02_sensors"}],
    }
    checks = MODULE.evaluate_live_contract(case, raw)
    assert all(checks.values())


def test_live_contract_accepts_parallel_tool_event_order() -> None:
    case = {
        "expected_calls": [
            {"server_id": "imes-readonly", "tool": "imes__get_current_previous_heat_si_summary", "arguments": {}},
            {"server_id": "gl02-data", "tool": "query_gl02_sensors", "arguments": {"variables": ["P_top"]}},
        ],
        "answer_contract": {"required_fields": [], "must_include": [], "must_not_include": []},
    }
    raw = {"ok": True, "events": ["final"], "answer": "事实",
           "tool_starts": [
               {"tool": "query_gl02_sensors", "arguments": {"variables": ["P_top"], "query_type": "latest"}},
               {"tool": "imes__get_current_previous_heat_si_summary", "arguments": {}},
           ],
           "source_status": [{"server_id": "gl02-data"}, {"server_id": "imes-readonly"}]}
    checks = MODULE.evaluate_live_contract(case, raw)
    assert checks["tool_selection"] is True
    assert checks["arguments"] is True
    assert checks["server_selection"] is True


def test_live_contract_accepts_explicit_tool_alternative_with_its_arguments() -> None:
    case = {
        "expected_calls": [{
            "tool": "find_gl02_variables",
            "arguments": {"keyword": "顶压"},
            "alternatives": [{"tool": "get_gl02_variable_info", "arguments": {"variable": "P_top"}}],
        }],
        "answer_contract": {"required_fields": [], "must_include": [], "must_not_include": []},
    }
    raw = {
        "ok": True,
        "events": ["final"],
        "answer": "P_top",
        "tool_starts": [{"tool": "get_gl02_variable_info", "arguments": {"variable": "P_top"}}],
    }
    checks = MODULE.evaluate_live_contract(case, raw)
    assert checks["tool_selection"] is True
    assert checks["arguments"] is True


def test_gold004_accepts_cached_object_confirmation_but_requires_query() -> None:
    case = {
        "case_id": "GOLD-004",
        "expected_calls": [
            {"tool": "find_gl02_variables", "arguments": {"keyword": "顶压"}, "optional": True},
            {"tool": "query_gl02_sensors", "arguments": {"variables": ["P_top"]}},
        ],
        "answer_contract": {"required_fields": [], "must_include": ["P_top"], "must_not_include": []},
    }
    raw = {
        "ok": True,
        "events": ["final"],
        "answer": "P_top 统计完成",
        "tool_starts": [{"tool": "query_gl02_sensors", "arguments": {"variables": ["P_top"]}}],
        "turns": [{"answer": "顶压标准变量是 P_top。"}, {"answer": "P_top 统计完成"}],
    }
    checks = MODULE.evaluate_live_contract(case, raw)
    assert all(checks.values())


def test_live_contract_reads_case_insensitive_si_and_chinese_statistics_fields() -> None:
    case = {
        "expected_calls": [],
        "answer_contract": {
            "required_fields": ["si_avg", "start_time", "end_time", "count"],
            "must_include": ["Si"],
            "must_not_include": [],
        },
    }
    raw = {
        "ok": True,
        "events": ["final"],
        "answer": "si_avg 0.42%；时间范围 10:00 至 11:00；样本数 59。",
        "tool_starts": [],
    }
    checks = MODULE.evaluate_live_contract(case, raw)
    assert all(checks.values())


def test_mock_report_explicitly_disclaims_live_production_success() -> None:
    report = {"evaluation_id": "x", "mode": "mocked", "pass_k": 1,
              "rows": [{"case_id": "GOLD-001", "run": 1, "status": "passed", "evaluation_layer": "mocked_contract_fixture", "checks": {}}]}
    markdown = MODULE.report_markdown(report)
    assert "不代表生产 MCP 或模型实测通过" in markdown


def test_gold005_not_found_is_oracle_invalid_instead_of_product_failure() -> None:
    case = {"case_id": "GOLD-005"}
    raw = {
        "tool_results": [{
            "tool": "imes__resolve_spoken_heat_reference",
            "result": {"error_code": "HEAT_REFERENCE_NOT_FOUND"},
        }],
    }
    assert MODULE.live_status(case, raw, {"tool_selection": False}) == "oracle_invalid"


def test_report_status_values_include_oracle_and_not_supported() -> None:
    assert {"passed", "failed", "error", "not_supported", "oracle_invalid"} == MODULE.STATUS_VALUES
