from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ASSISTANT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ASSISTANT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mcp_host.client_manager import McpClientManager, McpToolBinding, exposed_tool_name  # noqa: E402
from mcp_host.domain_router import select_mcp_servers  # noqa: E402
from mcp_host.server_registry import load_server_registry  # noqa: E402
import ollama_proxy_server as proxy  # noqa: E402


REGISTRY_PATH = BACKEND_DIR / "mcp_host" / "server_registry.json"


def test_registry_declares_local_mcp_services():
    registry = load_server_registry(REGISTRY_PATH)
    assert [item.server_id for item in registry.enabled_servers()] == [
        "gl02-data",
        "gl02-extended",
        "imes-readonly",
        "imes-web-readonly",
    ]
    assert all(item.script_path.is_file() for item in registry.enabled_servers())
    assert registry.by_id("gl02-data").default is True
    assert registry.by_id("imes-readonly").excluded_tools == ("query_imes_readonly_sql",)


def test_domain_router_selects_imes_without_attaching_gl02_for_heat_question():
    registry = load_server_registry(REGISTRY_PATH)
    selected = select_mcp_servers("当前属于第几个炉次？上一炉铁水硅平均值是多少？", registry)
    assert selected.server_ids == ("imes-readonly",)


def test_domain_router_can_select_both_services_for_cross_source_question():
    registry = load_server_registry(REGISTRY_PATH)
    selected = select_mcp_servers("上一炉出铁期间的顶压走势画出来", registry)
    assert selected.server_ids == ("gl02-data", "imes-readonly")


def test_domain_router_selects_extended_service_for_body_temperature_question():
    registry = load_server_registry(REGISTRY_PATH)
    selected = select_mcp_servers("查询炉身13层和C点温度", registry)
    assert selected.server_ids == ("gl02-extended",)


def test_domain_router_selects_web_adapter_only_for_explicit_web_request():
    registry = load_server_registry(REGISTRY_PATH)
    selected = select_mcp_servers("通过IMES Web查询今天的炉次化验", registry)
    assert selected.server_ids == ("imes-readonly", "imes-web-readonly")


def test_namespaced_imes_tools_do_not_collide_with_legacy_gl02_names():
    registry = load_server_registry(REGISTRY_PATH)
    assert exposed_tool_name(registry.by_id("gl02-data"), "query_gl02_sensors") == "query_gl02_sensors"
    assert exposed_tool_name(registry.by_id("imes-readonly"), "get_current_heat_context") == "imes__get_current_heat_context"


def test_live_imes_registration_exposes_arbitrary_heat_chemistry_schema():
    async def inspect_tools():
        registry = load_server_registry(REGISTRY_PATH)
        manager = McpClientManager(registry, sys.executable)
        async with manager:
            bindings = await manager.attach(("imes-readonly",))
            return next(
                item
                for item in bindings
                if item.exposed_name == "imes__query_heat_chemistry"
            )

    binding = asyncio.run(inspect_tools())
    assert binding.server_id == "imes-readonly"
    assert binding.input_schema["properties"]["heat_reference"]["type"] == "string"
    assert binding.input_schema["properties"]["components"]["anyOf"][0]["type"] == "array"


def test_client_manager_routes_exposed_name_to_native_server_tool():
    class FakeSession:
        async def call_tool(self, name, arguments):
            return {"name": name, "arguments": arguments}

    registry = load_server_registry(REGISTRY_PATH)
    manager = McpClientManager(registry, "python")
    manager._sessions["imes-readonly"] = FakeSession()
    manager._bindings["imes__native"] = McpToolBinding(
        exposed_name="imes__native",
        native_name="native",
        server_id="imes-readonly",
        description="",
        input_schema={"type": "object"},
    )
    result = asyncio.run(manager.call_tool("imes__native", {"heat_no": "2#1001"}))
    assert result == {"name": "native", "arguments": {"heat_no": "2#1001"}}


def test_frequent_heat_and_previous_si_question_uses_one_composite_tool():
    plan = proxy.qa_mcp_imes_plan("当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？")
    assert plan == {"tool": "imes__get_current_previous_heat_si_summary", "arguments": {}}


def test_current_heat_question_uses_current_heat_context_tool():
    plan = proxy.qa_mcp_imes_plan("现在属于第几个炉次？")
    assert plan == {"tool": "imes__get_current_heat_context", "arguments": {}}


def test_web_adapter_exposes_explicit_namespace():
    registry = load_server_registry(REGISTRY_PATH)
    assert exposed_tool_name(registry.by_id("imes-web-readonly"), "query_imes_web_dataset") == (
        "imesweb__query_imes_web_dataset"
    )


def test_imes_fact_question_enters_tool_loop_before_legacy_furnace_context_gate():
    question = "当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？"
    assert proxy.qa_mcp_should_use_tools(question, {}, {"used": False}) is True
    assert proxy.qa_mcp_imes_query_intent("某一个炉次的硅含量和锰成分") is True


def test_deterministic_imes_formatter_reports_sample_contract():
    answer = proxy.deterministic_mcp_answer(
        "imes__get_current_previous_heat_si_summary",
        '{"ok":true,"current_heat_no":"2#1002","previous_heat_no":"2#1001",'
        '"sample_count":3,"si_values":[0.2,0.3,0.25],"si_avg":0.25,"si_min":0.2,'
        '"si_max":0.3,"as_of_time":"2026-08-05T07:07:27"}',
    )
    assert "当前炉次：2#1002" in answer
    assert "上一炉次：2#1001" in answer
    assert "Si平均值为 0.25%" in answer
    assert "3 个有效试样" in answer


def test_model_selected_heat_chemistry_has_one_round_fact_formatter():
    answer = proxy.deterministic_mcp_answer(
        "imes__query_heat_chemistry",
        '{"ok":true,"resolved_heat_no":"2#20260805-065",'
        '"components":["si","mn"],"sample_count":2,'
        '"summary":{"si":{"count":2,"avg":0.37,"min":0.36,"max":0.38,"missing":false},'
        '"mn":{"count":1,"avg":0.22,"min":0.22,"max":0.22,"missing":false}},'
        '"samples":[{"sample_no":"B2","take_sample_time":"2026-08-05T05:54:00",'
        '"components":{"si":0.36,"mn":0.22}}],'
        '"data_time":"2026-08-05T06:11:00","source_service":"imes-readonly"}',
    )
    assert "炉次：2#20260805-065" in answer
    assert "Si：平均 0.37%" in answer
    assert "Mn：平均 0.22%" in answer
    assert "来源：imes-readonly" in answer



def test_current_spoken_heat_silicon_uses_partial_current_tool():
    plan = proxy.qa_mcp_imes_plan("当前鸬鹚的硅含量是多少？把三个试样都列出来")
    assert plan == {
        "tool": "imes__query_current_heat_chemistry",
        "arguments": {"components": ["si"]},
    }


def test_approximate_time_silicon_uses_time_range_tool():
    question = "昨天上午4点到7点左右是哪几个鸬鹚？看看每罐硅含量"
    plan = proxy.qa_mcp_imes_plan(question)
    assert plan == {
        "tool": "imes__query_heat_chemistry_by_time_range",
        "arguments": {
            "time_reference": question.replace("鸬鹚", "炉次"),
            "components": ["si"],
        },
    }
    registry = load_server_registry(REGISTRY_PATH)
    selection = select_mcp_servers(question, registry)
    assert "imes-readonly" in selection.server_ids


def test_current_heat_formatter_marks_partial_and_lists_tank_time():
    answer = proxy.deterministic_mcp_answer(
        "imes__query_current_heat_chemistry",
        '{"ok":true,"resolved_heat_no":"2#20260807-081","provisional":true,'
        '"open_time":"2026-08-07T05:10:00","close_time":null,'
        '"components":["si"],"summary":{"si":{"count":2,"avg":0.275,'
        '"min":0.26,"max":0.29,"missing":false}},'
        '"samples":[{"sample_no":"S1","tank_no":"T01",'
        '"sample_time":"2026-08-07T05:45:00","sample_time_type":"judge_time",'
        '"components":{"si":0.26}}],"data_time":"2026-08-07T06:00:00"}',
    )
    assert "正在出铁" in answer
    assert "阶段性统计" in answer
    assert "开口时间：2026-08-07T05:10:00" in answer
    assert "铁罐 T01" in answer
    assert "化验判定时间 2026-08-07T05:45:00" in answer


def test_time_range_formatter_lists_inferred_heat_and_samples():
    answer = proxy.deterministic_mcp_answer(
        "imes__query_heat_chemistry_by_time_range",
        '{"ok":true,"primary_heat_no":"2#20260806-079",'
        '"time_range":{"start":"2026-08-06T04:00:00","end":"2026-08-06T07:00:00"},'
        '"heats":[{"heat_no":"2#20260806-079","match_kind":"overlap",'
        '"open_time":"2026-08-06T04:30:00","close_time":"2026-08-06T05:30:00",'
        '"chemistry":{"summary":{"si":{"count":1,"avg":0.31,"min":0.31,"max":0.31}},'
        '"samples":[{"sample_no":"079-1","tank_no":"T079",'
        '"sample_time":"2026-08-06T05:00:00","sample_time_type":"judge_time",'
        '"components":{"si":0.31}}]}}],"source_service":"imes-readonly"}',
    )
    assert "最可能炉次：2#20260806-079" in answer
    assert "开口 2026-08-06T04:30:00" in answer
    assert "铁罐 T079" in answer
    assert "Si 0.31%" in answer
