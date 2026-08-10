from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mcp_tool_policy import ToolPolicyLimits, validate_tool_call  # noqa: E402
import ollama_proxy_server as proxy  # noqa: E402


QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "variables": {"type": "array", "items": {"type": "string"}},
        "query_type": {"type": "string", "enum": ["latest", "history", "statistics"]},
        "start_time": {"type": "string"},
        "end_time": {"type": "string"},
    },
    "required": ["variables"],
}
SCHEMAS = {"query_gl02_sensors": QUERY_SCHEMA}


def test_valid_model_planned_call_passes_live_schema_policy():
    result = validate_tool_call(
        "query_gl02_sensors",
        {"variables": ["P_top", "DP_total"], "query_type": "history"},
        SCHEMAS,
    )
    assert result["ok"] is True
    assert result["policy"] == "live_mcp_schema_readonly"


def test_unknown_tool_is_rejected_before_mcp_execution():
    result = validate_tool_call("execute_sql", {"sql": "select 1"}, SCHEMAS)
    assert result["ok"] is False
    assert result["error"] == "UNKNOWN_TOOL"


def test_schema_rejects_unknown_sql_argument():
    result = validate_tool_call(
        "query_gl02_sensors",
        {"variables": ["P_top"], "sql": "select * from secrets"},
        SCHEMAS,
    )
    assert result["ok"] is False
    assert any(item["code"] == "UNKNOWN_ARGUMENT" for item in result["errors"])


def test_schema_rejects_missing_required_argument_and_wrong_enum():
    missing = validate_tool_call("query_gl02_sensors", {"query_type": "latest"}, SCHEMAS)
    wrong_enum = validate_tool_call(
        "query_gl02_sensors",
        {"variables": ["P_top"], "query_type": "delete"},
        SCHEMAS,
    )
    assert any(item["code"] == "MISSING_REQUIRED" for item in missing["errors"])
    assert any(item["code"] == "ENUM_MISMATCH" for item in wrong_enum["errors"])


def test_policy_limits_array_and_argument_payload():
    array_result = validate_tool_call(
        "query_gl02_sensors",
        {"variables": ["P_top", "DP_total"]},
        SCHEMAS,
        ToolPolicyLimits(max_array_items=1),
    )
    payload_result = validate_tool_call(
        "query_gl02_sensors",
        {"variables": ["P_top"]},
        SCHEMAS,
        ToolPolicyLimits(max_argument_chars=10),
    )
    assert any(item["code"] == "ARRAY_TOO_LARGE" for item in array_result["errors"])
    assert payload_result["error"] == "ARGUMENTS_TOO_LARGE"


def test_multi_step_analysis_question_enters_model_planner():
    question = "分析最近两小时炉顶压力和总压差的关系并画出来"
    assert proxy.qa_mcp_agent_planning_intent(question) is True
    assert proxy.qa_mcp_should_use_tools(question, {}, {"used": False}) is True


def test_plain_process_knowledge_does_not_force_mcp_tools():
    question = "高炉内焦炭主要起什么作用？"
    assert proxy.qa_mcp_agent_planning_intent(question) is False
    assert proxy.qa_mcp_should_use_tools(question, {}, {"used": False}) is False


def test_streaming_entry_keeps_multi_round_tool_loop_enabled():
    source = (BACKEND_DIR / "ollama_proxy_server.py").read_text(encoding="utf-8")
    start = source.index("def handle_qa_chat_stream")
    streaming_block = source[start : start + 12_000]
    assert "stop_after_tool_round=False" in streaming_block
    assert "stop_after_tool_round=True" not in streaming_block


def test_spoken_arbitrary_heat_chemistry_enters_registered_tool_planner():
    question = "065炉的硅、锰、磷分别是多少？"
    assert proxy.qa_mcp_imes_query_intent(question) is True
    assert proxy.qa_mcp_should_use_tools(question, {}, {"used": False}) is True
    assert proxy.qa_mcp_imes_plan(question) is None


def test_planner_prompt_prefers_single_registered_heat_chemistry_call():
    prompt = proxy.QA_MCP_BRIDGE_SYSTEM_PROMPT
    assert "imes__query_heat_chemistry" in prompt
    assert "只能从本轮提供的已注册工具Schema中选择工具" in prompt
    assert "不得生成SQL" in prompt


def test_model_planner_sse_exposes_safe_structured_call_not_reasoning():
    source = (BACKEND_DIR / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert '"route": "model_planner"' in source
    assert '"planner_call": {' in source
    assert '"server_id": tool_servers.get(name)' in source


def test_arbitrary_heat_planner_catalog_uses_only_live_relevant_schemas():
    tools = [
        {"type": "function", "function": {"name": "imes__query_heat_chemistry"}},
        {"type": "function", "function": {"name": "imes__query_hot_metal_chemistry_by_heat"}},
        {"type": "function", "function": {"name": "imes__query_imes_variables"}},
        {"type": "function", "function": {"name": "query_gl02_sensors"}},
    ]
    selected = proxy.qa_mcp_planner_tools(
        "查询2#20260805-065炉次的C、Si、Mn、P、S", tools
    )
    assert [(item["function"]["name"]) for item in selected] == [
        "imes__query_heat_chemistry",
        "imes__query_hot_metal_chemistry_by_heat",
    ]
    assert all(item in tools for item in selected)
