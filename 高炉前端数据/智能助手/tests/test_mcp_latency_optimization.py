from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import ollama_proxy_server as proxy  # noqa: E402


def test_common_relationship_question_uses_one_composite_analysis_tool():
    plan = proxy.qa_mcp_standard_analysis_plan("分析最近半小时炉顶压力和总压差是否相关")
    assert plan is not None
    assert plan["tool"] == "plot_gl02_analysis"
    assert plan["arguments"]["variables"] == ["P_top", "DP_total"]
    assert plan["arguments"]["analysis_type"] == "correlation_scatter"
    assert plan["arguments"]["start_time"].endswith(":00+08:00")
    assert plan["arguments"]["end_time"].endswith(":00+08:00")


def test_planner_context_excludes_full_furnace_and_knowledge_system_payload():
    messages = [
        {
            "role": "system",
            "content": "完整炉况资料 SECRET_FURNACE_PAYLOAD\n知识证据 SECRET_RAG_PAYLOAD",
        },
        {"role": "user", "content": "看看顶压"},
        {"role": "assistant", "content": "你还要比较什么？"},
        {"role": "user", "content": "和总压差比较并分析相关性"},
    ]
    compact = proxy.qa_mcp_planner_messages(messages)
    text = "\n".join(str(item.get("content") or "") for item in compact)
    assert "SECRET_FURNACE_PAYLOAD" not in text
    assert "SECRET_RAG_PAYLOAD" not in text
    assert "和总压差比较并分析相关性" in text
    assert len(compact) <= proxy.QA_MCP_PLANNER_CONTEXT_MESSAGES + 1


def test_planner_defaults_are_low_temperature_and_small_output():
    assert proxy.QA_MCP_PLANNER_TEMPERATURE == 0
    assert proxy.QA_MCP_PLANNER_MAX_TOKENS <= 400
    assert proxy.QA_MCP_PLANNER_CONTEXT_MESSAGES <= 6
    assert proxy.QA_MCP_MAX_TOOL_ROUNDS == 2
    assert proxy.QA_MCP_MAX_TOOL_CALLS == 4
    assert proxy.QA_MCP_TOOL_TIMEOUT_SECONDS <= proxy.QA_MCP_EXECUTION_BUDGET_SECONDS


def test_tool_result_cache_reuses_success_and_skips_failure():
    old_ttl = proxy.QA_MCP_TOOL_CACHE_TTL_SECONDS
    try:
        proxy.QA_MCP_TOOL_CACHE_TTL_SECONDS = 30
        proxy._QA_MCP_TOOL_CACHE.clear()
        args = {"variables": ["P_top", "DP_total"], "query_type": "statistics"}
        proxy.qa_mcp_tool_cache_put("query_gl02_sensors", args, '{"ok": true, "count": 2}')
        assert proxy.qa_mcp_tool_cache_get("query_gl02_sensors", args) == '{"ok": true, "count": 2}'
        failed_args = {"variables": ["UNKNOWN"]}
        proxy.qa_mcp_tool_cache_put("query_gl02_sensors", failed_args, '{"ok": false, "error": "NO_DATA"}')
        assert proxy.qa_mcp_tool_cache_get("query_gl02_sensors", failed_args) is None
    finally:
        proxy.QA_MCP_TOOL_CACHE_TTL_SECONDS = old_ttl
        proxy._QA_MCP_TOOL_CACHE.clear()


def test_tool_loop_uses_compact_planner_settings():
    source = (BACKEND_DIR / "ollama_proxy_server.py").read_text(encoding="utf-8")
    start = source.index("async def qa_mcp_tool_loop_async")
    block = source[start : start + 18_000]
    assert "planner_messages = qa_mcp_planner_messages(working_messages)" in block
    assert "temperature=QA_MCP_PLANNER_TEMPERATURE" in block
    assert "max_tokens=QA_MCP_PLANNER_MAX_TOKENS" in block
    assert "asyncio.wait_for(" in block
    assert "tool_timeout_seconds()" in block
    assert '"deterministic_chart"' in block
    assert '"deterministic_sensor_query"' in block
    assert '"standard_composite_analysis"' in block
