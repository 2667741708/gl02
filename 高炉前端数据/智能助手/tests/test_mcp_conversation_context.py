from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mcp_conversation_context import (  # noqa: E402
    context_with_tool_trace,
    enrich_routing_question,
    infer_chart,
    update_tool_context,
)
import ollama_proxy_server as proxy  # noqa: E402


def test_first_turn_records_explicit_object_and_time():
    context = update_tool_context(None, "看下最近半小时顶压", ["P_top"], 30)
    assert context["selected_objects"] == ["P_top"]
    assert context["time_range"] == {"mode": "relative", "minutes": 30}
    assert context["analysis_goal"] == "history"
    assert context["inheritance"] == {"objects": False, "time_range": False}


def test_low_information_draw_followup_inherits_objects_and_time():
    previous = update_tool_context(None, "比较最近半小时顶压和总压差", ["P_top", "DP_total"], 30)
    context = update_tool_context(previous, "画出来", [], None)
    assert context["selected_objects"] == ["P_top", "DP_total"]
    assert context["time_range"]["minutes"] == 30
    assert context["analysis_goal"] == "plot"
    assert context["preferred_chart"] == "trend"
    assert context["inheritance"] == {"objects": True, "time_range": True}


def test_one_picture_followup_inherits_objects_and_time():
    previous = update_tool_context(None, "南北探尺最近一小时", ["L_south", "L_north"], 60)
    context = update_tool_context(previous, "一张图", [], None)
    assert context["selected_objects"] == ["L_south", "L_north"]
    assert context["time_range"]["minutes"] == 60
    assert context["preferred_chart"] == "trend"


def test_change_time_followup_keeps_objects_and_replaces_time():
    previous = update_tool_context(None, "顶压最近半小时", ["P_top"], 30)
    context = update_tool_context(previous, "换成两小时", [], 120)
    assert context["selected_objects"] == ["P_top"]
    assert context["time_range"]["minutes"] == 120
    assert context["inheritance"]["objects"] is True
    assert context["inheritance"]["time_range"] is False
    assert proxy.qa_mcp_duration_minutes("换成两小时\n[服务端对话状态：最近30分钟]") == 120


def test_add_object_followup_merges_with_previous_selection():
    previous = update_tool_context(None, "顶压最近半小时", ["P_top"], 30)
    context = update_tool_context(previous, "再加上总压差一起看", ["DP_total"], None)
    assert context["selected_objects"] == ["P_top", "DP_total"]
    assert context["time_range"]["minutes"] == 30


def test_new_multi_object_question_replaces_unrelated_previous_selection():
    previous = update_tool_context(None, "南探尺最近半小时", ["L_south"], 30)
    context = update_tool_context(
        previous,
        "炉顶压力和总压差是否相关",
        ["P_top", "DP_total"],
        None,
    )
    assert context["selected_objects"] == ["P_top", "DP_total"]
    assert context["time_range"] is None
    assert context["inheritance"] == {"objects": False, "time_range": False}


def test_leading_link_word_and_chart_change_are_followups():
    previous = update_tool_context(None, "顶压最近半小时", ["P_top"], 30)
    merged = update_tool_context(previous, "和总压差比较", ["DP_total"], None)
    changed = update_tool_context(merged, "换散点", [], None)
    assert merged["selected_objects"] == ["P_top", "DP_total"]
    assert changed["selected_objects"] == ["P_top", "DP_total"]
    assert changed["preferred_chart"] == "correlation_scatter"


def test_specific_correlation_heatmap_wins_over_generic_matrix():
    assert infer_chart("画相关矩阵", "correlation") == "correlation_heatmap"


def test_deterministic_chart_formatter_returns_factual_answer_without_model():
    answer = proxy.deterministic_mcp_answer(
        "plot_gl02_analysis",
        """{"ok":true,"variables":["P_top","DP_total"],"start_time":"2026-07-26T17:00:00+08:00",
        "end_time":"2026-07-26T17:30:00+08:00","derived":{"correlation":{"left":"P_top",
        "right":"DP_total","pearson_r":-0.33,"aligned_count":30}}}""",
    )
    assert "顶压" in answer
    assert "总压差" in answer
    assert "r=-0.33" in answer


def test_deterministic_latest_formatter_uses_formal_chinese_labels():
    answer = proxy.deterministic_mcp_answer(
        "query_gl02_sensors",
        """{"ok":true,"items":[
        {"requested_variable":"P_blast_cold","ok":true,"variable":{"unit":""},
         "latest":{"value":461.2,"ts":"2026-07-26T18:00:00"}},
        {"requested_variable":"O2_rate","ok":true,"variable":{},
         "latest":{"value":6.3,"ts":"2026-07-26T18:00:00"}}
        ]}""",
    )
    assert "冷风压力：461.2kPa" in answer
    assert "富氧率：6.3%" in answer


def test_private_routing_suffix_enables_deterministic_chart_without_changing_user_text():
    previous = update_tool_context(None, "比较最近半小时顶压和总压差", ["P_top", "DP_total"], 30)
    context = update_tool_context(previous, "画出来", [], None)
    routing = enrich_routing_question("画出来", context)
    plan = proxy.qa_mcp_chart_plan(routing)
    assert routing.startswith("画出来\n[服务端对话状态：")
    assert plan is not None
    assert plan["tool"] == "plot_gl02_trends"
    assert plan["arguments"]["variables"] == ["P_top", "DP_total"]


def test_latest_private_intent_does_not_accidentally_trigger_chart_route():
    context = update_tool_context(None, "冷风管道压力现在是多少", ["P_blast_cold"], None)
    routing = enrich_routing_question("冷风管道压力现在是多少", context)
    assert "查询意图：latest" in routing
    assert proxy.qa_mcp_chart_plan(routing) is None
    assert proxy.qa_mcp_sensor_query_plan(routing) == {
        "tool": "query_gl02_sensors",
        "arguments": {"variables": ["P_blast_cold"], "query_type": "latest"},
    }


def test_tool_trace_is_compacted_into_next_turn_context():
    context = update_tool_context(None, "顶压趋势图", ["P_top"], 60)
    updated = context_with_tool_trace(
        context,
        [
            {
                "tool": "plot_gl02_trends",
                "result": {"image_url": "/data/mcp_charts/example.png", "count": 61},
            }
        ],
    )
    assert updated["last_tool_names"] == ["plot_gl02_trends"]
    assert updated["last_evidence"][0]["image_url"].endswith("example.png")
