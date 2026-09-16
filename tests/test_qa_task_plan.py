from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "高炉前端数据" / "智能助手" / "backend" / "qa_task_plan.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("qa_task_plan", MODULE_PATH)
assert SPEC and SPEC.loader
qa_task_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa_task_plan)


def test_document_word_inside_title_does_not_trigger_live_tools() -> None:
    plan = qa_task_plan.build_task_plan("请按原文完整说明《高炉风量曲线操作规程》")
    assert plan["primary_intent"] == "document_knowledge"
    assert plan["search_knowledge"] is True
    assert plan["allow_prefetch"] is False
    assert plan["allow_mcp_tools"] is False
    assert plan["allowed_sources"] == ["knowledge_base"]


def test_document_and_explicit_current_data_can_form_compound_plan() -> None:
    plan = qa_task_plan.build_task_plan("先按原文说明《炉顶压力制度》，再查询当前炉顶压力是多少")
    assert plan["intents"] == ["document_knowledge", "live_data"]
    assert plan["search_knowledge"] is True
    assert plan["allow_prefetch"] is True
    assert plan["allow_mcp_tools"] is True


def test_history_is_not_treated_as_live_process_data() -> None:
    plan = qa_task_plan.build_task_plan("列出我最近问过什么问题")
    assert plan["primary_intent"] == "conversation_history"
    assert plan["allowed_tool_domains"] == ["conversation_history"]
    assert plan["allow_prefetch"] is False
    assert plan["search_knowledge"] is False


def test_user_data_analysis_disables_live_lookup() -> None:
    plan = qa_task_plan.build_task_plan("只用我提供的风温数据分析趋势，不要查询现场数据库")
    assert plan["no_live_lookup"] is True
    assert plan["primary_intent"] == "user_supplied_data"
    assert plan["allow_mcp_tools"] is False
    assert plan["allow_prefetch"] is False


def test_no_live_general_explanation_can_still_use_knowledge() -> None:
    plan = qa_task_plan.build_task_plan("顶压升高通常可能有哪些原因？不要查询实时数据。")
    assert plan["primary_intent"] == "general_knowledge"
    assert plan["search_knowledge"] is True
    assert plan["allow_mcp_tools"] is False


def test_ordinary_explanation_needs_no_tool() -> None:
    plan = qa_task_plan.build_task_plan("为什么提高风温通常能够降低焦比？")
    assert plan["primary_intent"] == "general_knowledge"
    assert plan["search_knowledge"] is True
    assert plan["allow_mcp_tools"] is False


def test_short_colloquial_live_value_request_uses_readonly_data() -> None:
    for question in ("俩铁口温度。", "给我说一下炉顶的压力"):
        plan = qa_task_plan.build_task_plan(question)
        assert plan["primary_intent"] == "live_data"
        assert plan["allow_prefetch"] is True
        assert plan["allow_mcp_tools"] is True


def test_public_plan_does_not_expose_question_or_quotes() -> None:
    plan = qa_task_plan.build_task_plan("请说明《内部标题》")
    public = qa_task_plan.public_task_plan(plan)
    assert "instruction_text" not in public
    assert "quoted_spans" not in public
    assert public["quoted_span_count"] == 1


def test_task_plan_freezes_all_explicit_live_entities() -> None:
    plan = qa_task_plan.build_task_plan("炉顶CO、CO2、H2现在分别是多少？")
    assert plan["entities"] == ["CO_top", "CO2_top", "H2_top"]
    public = qa_task_plan.public_task_plan(plan)
    assert public["entities"] == plan["entities"]


def test_temporal_failed_cases_pass_the_outer_tool_gate():
    for question in ("对比最近30分钟和前30分钟的炉顶压力。", "全炉压差最近一小时相对历史基线偏高吗？"):
        plan = qa_task_plan.build_task_plan(question)
        assert plan["intents"] == ["live_data"] and plan["allow_mcp_tools"]
        assert qa_task_plan.tool_allowed("query_gl02_sensors", plan)
        assert qa_task_plan.tool_allowed("query_gl02_feature_statistics", plan)
    plan = qa_task_plan.build_task_plan("炉顶压力历史基线的含义是什么？")
    assert not plan["allow_mcp_tools"]
    plan = qa_task_plan.build_task_plan("对比最近30分钟和前30分钟的炉顶压力，不要调用实时工具")
    assert not plan["allow_mcp_tools"]


def test_entities_inside_document_title_do_not_enter_execution_plan() -> None:
    plan = qa_task_plan.build_task_plan("请按原文说明《炉顶CO、CO2、H2操作规程》")
    assert plan["primary_intent"] == "document_knowledge"
    assert plan["entities"] == []


def test_tool_domains_are_enforced_after_intent_selection() -> None:
    history = qa_task_plan.build_task_plan("检索历史问答里关于透气性的回答")
    assert qa_task_plan.tool_allowed("search_qa_messages", history)
    assert not qa_task_plan.tool_allowed("query_gl02_statistics", history)
    document = qa_task_plan.build_task_plan("请按原文说明《风量曲线制度》")
    assert not qa_task_plan.tool_allowed("search_qa_messages", document)
    assert not qa_task_plan.tool_allowed("query_gl02_statistics", document)
    live = qa_task_plan.build_task_plan("查询当前炉顶压力")
    assert qa_task_plan.tool_allowed("query_gl02_statistics", live)
    assert not qa_task_plan.tool_allowed("search_qa_messages", live)
    assert not qa_task_plan.tool_allowed("update_furnace_setting", live)


def test_tool_safety_is_an_exact_allowlist_not_a_name_prefix_guess() -> None:
    live = qa_task_plan.build_task_plan("查询当前炉顶压力")
    assert qa_task_plan.tool_allowed("query_gl02_statistics", live)
    assert qa_task_plan.tool_allowed("imes__query_current_heat_chemistry", live)
    for disguised_write in (
        "get_update_furnace_setting",
        "query_and_write",
        "list_then_delete",
        "calculate_and_execute",
    ):
        assert qa_task_plan.tool_domain(disguised_write) == "restricted_unknown"
        assert not qa_task_plan.tool_allowed(disguised_write, live)
