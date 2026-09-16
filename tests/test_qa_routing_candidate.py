from __future__ import annotations

import ast
import asyncio
import importlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / ".codex_runtime" / "qa-routing-v3" / "candidate"
SOURCE = (CANDIDATE / "ollama_proxy_server.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
NODES = {node.name: node for node in TREE.body if isinstance(node, ast.FunctionDef)}
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
sys.path.insert(0, str(BACKEND))
qa_task_plan = importlib.import_module("qa_task_plan")
sys.path.insert(0, str(CANDIDATE))
mcp_tool_selection = importlib.import_module("mcp_tool_selection")


def _knowledge_scope():
    scope = {
        "Any": object,
        "qa_task_plan": qa_task_plan,
        "QA_KNOWLEDGE_INTENT_GATE": True,
        "QA_ANSWER_ROUTE_CODE": "code_generation",
        "QA_ANSWER_ROUTE_ANALYSIS": "mcp_grounded_analysis",
        "qa_answer_route": lambda _: "direct",
        "normalize_spoken_question": lambda value: value,
        "qa_is_current_furnace_context_question": lambda _: False,
    }
    node = NODES["qa_should_search_knowledge"]
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<routing-candidate>", "exec"), scope)
    return scope


def test_document_plan_wins_even_when_title_contains_live_words() -> None:
    scope = _knowledge_scope()
    question = "请按原文完整说明《当前风量曲线操作规程》"
    plan = qa_task_plan.build_task_plan(question)
    assert scope["qa_should_search_knowledge"](question, {"used": True}, plan)[0] is True
    assert plan["allow_mcp_tools"] is False


def test_live_plan_skips_general_knowledge_search() -> None:
    scope = _knowledge_scope()
    question = "查询当前炉顶压力是多少"
    plan = qa_task_plan.build_task_plan(question)
    assert scope["qa_should_search_knowledge"](question, {"used": True}, plan)[0] is False
    assert plan["allow_mcp_tools"] is True


def test_ordinary_smalltalk_skips_retrieval_and_tools() -> None:
    scope = _knowledge_scope()
    question = "你好"
    plan = qa_task_plan.build_task_plan(question)
    assert scope["qa_should_search_knowledge"](question, None, plan)[0] is False
    assert plan["allow_mcp_tools"] is False


def test_request_flow_has_single_plan_for_prefetch_knowledge_and_tools() -> None:
    assert "task_plan = qa_task_plan.build_task_plan(question)" in SOURCE
    assert 'elif task_plan.get("allow_prefetch")' in SOURCE
    assert 'task_plan=task_plan' in SOURCE
    assert 'else bool(task_plan.get("allow_mcp_tools"))' in SOURCE
    assert '"qa_task_plan": qa_task_plan.public_task_plan(task_plan)' in SOURCE
    assert "if available and qa_task_plan.tool_allowed(name, task_plan)" in SOURCE
    assert 'if tool_selection.get("mode") == "required":' in SOURCE
    assert "if not qa_task_plan.tool_allowed(name, task_plan)" in SOURCE
    assert '"reason": "task_plan_forced_tool_rejected"' in SOURCE


def _run_loop_scope(async_loop):
    scope = {
        "Any": object,
        "Mapping": dict,
        "QA_RESPONSE_MODE_FLASH": "flash",
        "asyncio": asyncio,
        "qa_mcp_tool_loop_async": async_loop,
        "lifecycle_error": lambda stage, exc: {"stage": stage, "error_type": type(exc).__name__},
        "tool_result_succeeded": mcp_tool_selection.tool_result_succeeded,
        "deterministic_evidence_summary": mcp_tool_selection.deterministic_evidence_summary,
    }
    node = NODES["run_qa_mcp_tool_loop"]
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<routing-candidate>", "exec"), scope)
    return scope


def test_lifecycle_failure_preserves_already_verified_facts() -> None:
    async def fail_after_success(*args, evidence_sink=None, **kwargs):
        evidence_sink.append({"name": "query", "result_text": '{"ok":true,"P_top":42.5}'})
        raise RuntimeError("late failure")

    result = _run_loop_scope(fail_after_success)["run_qa_mcp_tool_loop"]([])
    assert result["ok"] is True
    assert result["grounding_status"] == "partial_verified_evidence"
    assert "P_top" in result["answer"]
    assert result["error_detail"]["error_type"] == "RuntimeError"


def test_lifecycle_failure_without_evidence_remains_failed_closed() -> None:
    async def fail_without_evidence(*args, **kwargs):
        raise RuntimeError("early failure")

    result = _run_loop_scope(fail_without_evidence)["run_qa_mcp_tool_loop"]([])
    assert result["ok"] is False
    assert result["answer"] == ""


def test_deterministic_facts_are_not_wrapped_as_code() -> None:
    result = mcp_tool_selection.deterministic_evidence_summary(
        [{"name": "query", "result_text": json.dumps({"ok": True, "P_top": 42.5})}]
    )
    assert "P_top" in result
    assert "```" not in result


def test_candidate_grounding_accepts_rounding_and_rejects_wrong_field() -> None:
    evidence = '{"P_top":{"avg":42.500123}}'
    assert mcp_tool_selection.answer_is_grounded("炉顶压力均值42.5。", evidence)
    assert not mcp_tool_selection.answer_is_grounded("炉顶温度均值42.5。", evidence)


def test_build_report_is_hash_bound_and_local_only() -> None:
    report = json.loads((CANDIDATE / "build.json").read_text(encoding="utf-8"))
    assert report["proxy_baseline_sha256"] == "c94dc585cd0d319ae9ef2235620acd7802d880f569510dac43c2e571a0e6298c"
    assert report["selection_baseline_sha256"] == "50eded25f48e7bedde8953e5120e406daaf6682acff2399e93bcb7864e684033"
    assert report["syntax"] == "passed"
    assert report["production_changed"] is False


def test_confirmed_regression_cases_follow_expected_source_domains() -> None:
    ledger = json.loads((ROOT / "tests/qa_regression/question_ledger_20260916.json").read_text(encoding="utf-8"))
    rows = {item["case_id"]: item for item in ledger["rows"]}
    document_ids = {
        "TPL-11F6C2E3DDD207BC", "TPL-DE3A348E8836BC03", "TPL-48827B99541672E2",
        "TPL-9AB9414BFC82E504", "TPL-2941ED6E73448D66",
    }
    history_ids = {"TPL-FD3912331A49B991", "TPL-3877C5B34E972AA0", "TPL-4EB4CE7FC45519A5"}
    live_ids = {"TPL-00F9E60C73D8BE83", "TPL-A60B0CD794D49E48"}
    for case_id in document_ids:
        plan = qa_task_plan.build_task_plan(rows[case_id]["prompt"])
        assert plan["primary_intent"] == "document_knowledge", case_id
        assert plan["allowed_sources"] == ["knowledge_base"], case_id
        assert plan["allow_mcp_tools"] is False, case_id
    for case_id in history_ids:
        plan = qa_task_plan.build_task_plan(rows[case_id]["prompt"])
        assert plan["primary_intent"] == "conversation_history", case_id
        assert plan["allowed_tool_domains"] == ["conversation_history"], case_id
        assert plan["allow_prefetch"] is False, case_id
    for case_id in live_ids:
        plan = qa_task_plan.build_task_plan(rows[case_id]["prompt"])
        assert plan["primary_intent"] == "live_data", case_id
        assert plan["allowed_tool_domains"] == ["live_readonly_data"], case_id
