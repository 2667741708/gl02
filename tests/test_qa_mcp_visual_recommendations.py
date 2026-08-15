from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _proxy():
    return importlib.import_module("ollama_proxy_server")


def _source() -> str:
    return HTML.read_text(encoding="utf-8")


def test_spoken_matrix_heatmap_uses_one_deterministic_chart_tool() -> None:
    plan = _proxy().qa_mcp_chart_plan(
        "绘制最近一小时第7层到第13层A到H炉体温度矩阵热度图，每格显示当前温度和变化趋势。"
    )
    assert plan is not None
    assert plan["tool"] == "plot_gl02_body_temperature_matrix"
    assert plan["arguments"]["start_layer"] == 7
    assert plan["arguments"]["end_layer"] == 13
    assert plan["arguments"]["positions"] == list("ABCDEFGH")


def test_chart_link_is_appended_as_same_origin_mcp_markdown() -> None:
    answer = _proxy().append_mcp_chart_links(
        "已生成炉体温度矩阵。",
        [
            {
                "result": {
                    "ok": True,
                    "image_url": "/data/mcp_charts/body_temperature_matrix_20260814.png",
                }
            }
        ],
    )
    assert "![MCP数据图](/data/mcp_charts/body_temperature_matrix_20260814.png)" in answer


def test_ui_renders_only_bounded_same_origin_mcp_png_markers() -> None:
    source = _source()
    assert "function qaMcpChartParts" in source
    assert r"\/data\/mcp_charts\/" in source
    assert "[A-Za-z0-9._-]+\\.png" in source
    assert '<img src={part.value} alt="MCP 炉体温度矩阵热力图"' in source
    assert 'rel="noopener noreferrer"' in source
    assert "http.*mcp_charts" not in source[source.index("function qaMcpChartParts"):source.index("function QaMarkdown")]


def test_recommendation_library_is_scrollable_pinnable_and_customizable() -> None:
    source = _source()
    assert "QA_MCP_RECOMMENDED_PROMPTS" in source
    assert source.count("绘制最近一小时第7层到第13层A到H炉体温度矩阵热度图") == 1
    assert "qa-prompt-scroll" in source
    assert "overflow-y:auto" in source
    assert "固定问题" in source
    assert "添加自定义问题" in source
    assert "QA_PROMPT_PREFERENCES_KEY = 'bf_qa_prompt_preferences_v1'" in source
    assert "localStorage.setItem(QA_PROMPT_PREFERENCES_KEY" in source
    assert "不会覆盖其他局域网访客的偏好" in source


def test_original_common_questions_are_preserved_before_mcp_templates() -> None:
    source = _source()
    recommendation_start = source.index("function QaPromptRecommendations(")
    recommendation_end = source.index("function qaEnsurePromptRecommendationStyle", recommendation_start)
    recommendation = source[recommendation_start:recommendation_end]
    persistent_start = source.index("QaPromptRecommendations = function QaPromptRecommendationsPersistent")
    persistent_end = source.index("function QaGuestNav", persistent_start)
    persistent = source[persistent_start:persistent_end]

    assert "title: '原有常用问题'" in recommendation
    assert "title: '常用 MCP 模板'" in recommendation
    assert recommendation.index("title: '原有常用问题'") < recommendation.index("title: '常用 MCP 模板'")
    assert 'aria-label="可滚动推荐问题列表"' in recommendation
    assert 'tabIndex="0"' in recommendation
    assert "common={qaUniqueQuestions(props.common || [], 20)}" in persistent
    assert "mcpCommon={QA_MCP_RECOMMENDED_PROMPTS}" in persistent
    assert "[...QA_MCP_RECOMMENDED_PROMPTS, ...(props.common || [])]" not in persistent


def test_successful_final_answer_publishes_related_questions_without_resend() -> None:
    source = _source()
    stream_start = source.index("async function qaServerChatStream")
    stream_end = source.index("function qaMergeExecutionTrace", stream_start)
    stream = source[stream_start:stream_end]
    assert "qaPublishRelatedMcpQuestions(payload?.message)" in stream
    assert "bf:qa-related-mcp-questions" in source
    assert "qaRelatedMcpQuestions" in source
    assert "fetch('/api/qa/chat'" in stream
    assert stream.count("fetch('/api/qa/chat'") == 1
