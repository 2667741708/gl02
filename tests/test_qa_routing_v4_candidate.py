from __future__ import annotations

import ast
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "高炉前端数据" / "智能助手" / "backend"))
import qa_time_window_plan
import qa_report_workflow


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / ".codex_runtime" / "qa-routing-v4" / "candidate"


def test_v4_candidate_uses_shared_entity_resolver() -> None:
    source = (CANDIDATE / "ollama_proxy_server.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "import qa_entity_resolution" in source
    assert "entity_resolution = qa_entity_resolution.resolve_requested_entities(question)" in source
    assert 'variables = list(entity_resolution.get("variables") or [])' in source


def test_v4_build_is_hash_bound_to_accepted_v3() -> None:
    report = json.loads((CANDIDATE / "build.json").read_text(encoding="utf-8"))
    assert report["proxy_baseline_sha256"] == "abd7cc463c42a7e1c707e1b840b33c9040b33cb850ac7719b164732329af6e67"
    assert report["task_plan_baseline_sha256"] == "bc34986d7a8cb7ff5af11d073809fce623b4cd924865484d5bf98cd9255510e8"
    assert report["mcp_baseline_sha256"] == "35e35f540077e615d5a6213b3a81dbaf875be6d7257d4428ae2b2acb6a6bee31"
    assert report["issues"] == ["QAOPT-R03", "QAOPT-R04", "QAOPT-R05"]
    assert report["syntax"] == "passed"
    assert report["production_changed"] is False


def test_proxy_temporal_seam_executes_serially_and_commits_each_result():
    tree = ast.parse((CANDIDATE / "ollama_proxy_server.py").read_text(encoding="utf-8"))
    seam = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                and ast.unparse(node.test) == "time_window_plan is not None or report_plan is not None")
    # Execute the actual candidate seam without importing unrelated production
    # modules. No reimplementation of the adapter under test.
    fn = ast.AsyncFunctionDef(name="run_seam", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]), body=seam.body, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    plan = qa_time_window_plan.build_time_window_plan("对比最近30分钟和前30分钟炉顶压力", ["P_top"], anchor=datetime(2026, 9, 16, 10, tzinfo=timezone(timedelta(hours=8))))
    calls, messages, evidence, events = [], [], [], []
    async def call_tool(session, name, args):
        calls.append((name, args))
        if len(calls) == 2:
            raise TimeoutError()
        return {"ok": True, "items": [{"requested_variable": "P_top", "result": {
            "ok": True, "variable": {"variable_name": "P_top", "unit": "kPa"},
            "start_time": args["start_time"], "end_time": args["end_time"],
            "statistics": {"avg": 123, "count": 30}, "source": {"type": "postgresql"}}}]}
    env = {"asyncio": asyncio, "json": json, "qa_time_window_plan": qa_time_window_plan,
           "time_window_plan": plan, "report_plan": None, "qa_report_workflow": qa_report_workflow, "qa_request_control": SimpleNamespace(call_tool=call_tool), "session": object(),
           "tool_timeout_seconds": lambda: 2, "try_load_json": json.loads, "mcp_result_to_text": lambda result, **kwargs: json.dumps(result),
           "working_messages": messages, "evidence_sink": evidence, "tool_names": {"query_gl02_sensors"},
           "tool_schemas": {}, "policy_limits": object(), "tool_servers": {"query_gl02_sensors": "gl02-data"},
           "validate_tool_call": lambda *args: {"ok": True}, "QA_MCP_MAX_TOOL_CALLS": 3,
           "qa_mcp_public_trace": lambda *args: {},
           "emit": lambda event, payload: events.append(event)}
    exec(compile(module, "candidate_temporal_seam", "exec"), env)
    result = asyncio.run(env["run_seam"]())
    assert len(calls) == 2 and len(evidence) == 2
    assert events == ["tool_start", "tool_result", "tool_start", "tool_result"]
    assert len(messages) == 4 and "123" in evidence[0]["result_text"]
    assert result["model_request_count"] == 0 and not result["complete"]
    assert "均值 123" in result["answer"]


def test_proxy_prefetch_never_consumes_temporal_query():
    tree = ast.parse((CANDIDATE / "ollama_proxy_server.py").read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "qa_mcp_prefetch")
    env = {"Any": object, "qa_evidence_policy": SimpleNamespace(no_live_lookup=lambda q: False), "qa_time_window_plan": qa_time_window_plan}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), "candidate_prefetch", "exec"), env)
    result = env["qa_mcp_prefetch"]("对比最近30分钟和前30分钟的炉顶压力")
    assert not result["used"] and result["reason"] == "requires_complete_temporal_workflow"
