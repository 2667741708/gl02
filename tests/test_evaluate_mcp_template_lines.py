from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex" / "skills" / "agent-tool-capability-evaluation" / "scripts" / "evaluate_mcp_template_lines.py"
SPEC = importlib.util.spec_from_file_location("evaluate_mcp_template_lines", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def write_catalog(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "objects": [
                    {"object_id": "P_top", "display_name": "顶压", "semantic_aliases": ["炉顶压力"]},
                    {"object_id": "DP_total", "display_name": "全炉压差", "semantic_aliases": ["总压差"]},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_parse_keeps_line_numbers_skips_placeholders_and_marks_duplicates(tmp_path: Path) -> None:
    template = tmp_path / "template.md"
    catalog = tmp_path / "catalog.json"
    write_catalog(catalog)
    template.write_text(
        "# 模板\n\n## 最新值\n```text\n现在顶压多少？\n现在顶压多少？\n查询 {variable} 当前值\n助手：这是答案\n```\n",
        encoding="utf-8",
    )
    rows = MODULE.parse_template(template, catalog)
    assert [row["source_line"] for row in rows] == [5, 6, 7, 8]
    assert [row["source_status"] for row in rows] == ["ready", "duplicate", "skipped", "skipped"]
    assert rows[0]["expected"]["objects"] == ["P_top"]
    assert rows[1]["duplicate_of"] == rows[0]["case_id"]


def test_parse_skips_failure_wording_examples_and_catalog_oracle_is_explicit(tmp_path: Path) -> None:
    template = tmp_path / "template.md"
    catalog = tmp_path / "catalog.json"
    write_catalog(catalog)
    template.write_text(
        "# 模板\n```text\n多样品：按发布时间从新到旧列出。\n静压力现在能查哪些点？\n```\n",
        encoding="utf-8",
    )
    rows = MODULE.parse_template(template, catalog)
    assert rows[0]["source_status"] == "skipped"
    assert "catalog" in rows[1]["expected"]["capabilities"]
    assert "find_gl02_variables" in rows[1]["expected"]["tool_families"][0]


def test_compare_separates_tool_contract_and_answer_fidelity() -> None:
    row = {
        "expected": {
            "objects": ["P_top"],
            "capabilities": ["statistics", "calculation"],
            "tool_families": ["query_gl02_sensors|query_gl02_statistics"],
        }
    }
    raw = {
        "ok": True,
        "events": ["tool_start", "tool_result", "final"],
        "answer": "顶压均值 250。",
        "tool_starts": [{"tool": "query_gl02_sensors", "arguments": {"variables": ["P_top"]}}],
        "tool_results": [{"tool": "query_gl02_sensors", "result": {"avg": 250, "start_time": "2026-08-13T10:00:00"}}],
    }
    result = MODULE.compare_row(row, raw)
    comparison = result["comparison"]
    assert comparison["tool_contract_passed"] is True
    assert comparison["final_answer_evidence_fidelity_passed"] is False
    assert comparison["core_evaluations"]["deterministic_tool_augmented_computation"]["status"] == "failed"
    assert comparison["issue_class"] == "answer_contract_failed"


def test_compare_classifies_missing_advertised_tool_and_runtime_error() -> None:
    row = {"expected": {"objects": [], "capabilities": ["report"], "tool_families": ["list_recent_reports"]}}
    unsupported = MODULE.compare_row(row, {"ok": True, "events": ["final"], "answer": "暂无"})
    assert unsupported["comparison"]["issue_class"] == "advertised_not_supported"
    runtime = MODULE.compare_row(row, {"ok": False, "events": ["error"], "answer": ""})
    assert runtime["comparison"]["issue_class"] == "runtime_error"


def test_catalog_question_using_catalog_tool_is_not_marked_implementation_defect() -> None:
    row = {"prompt": "静压力现在能查哪些点？", "expected": {"objects": [], "capabilities": ["catalog", "latest"],
            "tool_families": ["find_gl02_variables", "query_gl02_sensors"]}}
    raw = {"ok": True, "events": ["final"], "answer": "来源：gl02-data；可用点位列表。",
           "tool_starts": [{"tool": "find_gl02_variables", "arguments": {"keyword": "静压力"}}]}
    result = MODULE.compare_row(row, raw)
    assert result["comparison"]["tool_family_match"] is True
    assert result["comparison"]["issue_class"] != "implementation_defect"


def test_checkpoint_resume_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.jsonl"
    MODULE.append_checkpoint(path, {"case_id": "a", "status": "passed"})
    MODULE.append_checkpoint(path, {"case_id": "b", "status": "failed"})
    assert MODULE.load_checkpoint(path) == [
        {"case_id": "a", "status": "passed"},
        {"case_id": "b", "status": "failed"},
    ]


def test_existing_raw_row_can_be_reclassified_without_new_request() -> None:
    row = {"request_count": 1, "prompt": "当前日报有哪些？",
           "expected": {"objects": [], "capabilities": ["report"], "tool_families": ["list_recent_reports"]},
           "raw": {"ok": True, "events": ["final"], "answer": "暂无"}}
    result = MODULE.recompare_checkpoint_row(row)
    assert result["request_count"] == 1
    assert result["comparison"]["issue_class"] == "advertised_not_supported"


def test_real_template_inventory_is_stable_and_contains_four_core_cases() -> None:
    rows = MODULE.parse_template(
        ROOT / "PT" / "MCP可执行功能及口语调用模板.md",
        ROOT / "数据库同步和存取" / "config" / "点位语义目录.json",
    )
    assert len(rows) >= 150
    assert any("[MCP评估T1]" in row["prompt"] for row in rows)
    assert any("[MCP评估T2]" in row["prompt"] for row in rows)
    assert any("[MCP评估T3]" in row["prompt"] for row in rows)
    assert all(row["case_id"].startswith("L") for row in rows)
