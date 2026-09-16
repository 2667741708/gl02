"""Deterministic task planning before knowledge and tool routing.

REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916

The planner separates the user's instruction from quoted document text.  It is
pure and deliberately conservative: a source is enabled only when the outer
instruction needs it.  Model tool planning remains downstream of this gate.
"""
from __future__ import annotations

import re
from typing import Any

import qa_entity_resolution
import qa_time_window_plan


VERSION = "qa-task-plan-v2"

_QUOTED_RE = re.compile(r"“[^”]*”|‘[^’]*’|\"[^\"]*\"|'[^']*'|《[^》]*》")
_DOCUMENT_TERMS = (
    "三规二制", "原文", "全文", "逐条", "完整说明", "制度", "规程", "手册",
    "文档", "条款", "章节", "操作规程", "安全规程", "技术规程",
)
_DOCUMENT_ACTIONS = ("说明", "解释", "摘要", "总结", "读取", "列出", "引用", "查找", "检索", "给出", "回答", "是什么", "有哪些")
_HISTORY_TERMS = (
    "历史问答", "历史会话", "聊天记录", "对话记录", "之前问", "以前问", "问过", "问过什么",
    "最近问", "上一轮", "上次对话", "我们的对话",
)
_REPORT_TERMS = ("日报", "周报", "月报", "报表", "生产报告", "报告篮", "生成报告", "导出报告")
_LIVE_TERMS = (
    "当前", "现在", "目前", "最新", "实时", "今日", "今天", "昨天", "最近",
    "趋势", "走势", "曲线", "炉次", "炉号", "化验", "成分", "传感器", "数据库",
    "炉顶压力", "顶压", "压力", "铁口温度", "铁口", "温度", "风量", "风温", "压差",
    "p_top", "dp_", "gasutil", "t_top", "pci",
)
_LIVE_ACTIONS = (
    "查询", "查看", "读取", "调取", "检索", "分析", "判断", "统计", "计算",
    "平均", "最大", "最小", "变化", "是多少", "多少", "有没有", "是否",
    "说一下", "告诉我", "给我说", "给出",
)
_KNOWLEDGE_TERMS = (
    "原理", "机理", "原因", "为什么", "含义", "解释", "工艺", "规则", "阈值",
    "依据", "知识", "如何", "怎么", "方案", "报警", "告警",
)
_NO_LIVE_PATTERN = re.compile(r"(?:不要|不需要|无需|不必|不用|禁止|不)\s*(?:查(?:询)?|读取|访问|调用|检索|连接)[^，。；;\n]{0,12}(?:实时|现场|生产|数据库|数据|工具)")
_USER_DATA_PATTERN = re.compile(r"(?:只|仅)(?:用|看|根据|依据|基于)[^，。；;\n]{0,16}(?:我给|我提供|这些数|假设|已给|提供的)")

# The production MCP registry is read-only, but routing must not infer safety
# from a verb-shaped tool name.  Keep an explicit allowlist of exposed names;
# a newly registered tool remains unavailable until this list and its tests are
# reviewed together.
_HISTORY_TOOL_NAMES = {"search_qa_messages"}
_REPORT_TOOL_NAMES = {"list_recent_reports", "read_report_excerpt"}
_LIVE_READONLY_TOOL_NAMES = {
    "query_bf2_operation_log_report",
    "list_business_objects",
    "search_business_objects",
    "get_business_object",
    "find_gl02_variables",
    "get_gl02_variable_info",
    "list_gl02_available_variables",
    "get_latest_gl02_value",
    "query_gl02_history",
    "query_gl02_statistics",
    "query_gl02_sensors",
    "query_gl02_feature_statistics",
    "plot_gl02_trends",
    "plot_gl02_body_temperature_matrix",
    "plot_gl02_analysis",
    "get_latest_furnace_snapshot",
    "gl02ext__query_furnace_diagnosis_history",
    "gl02ext__query_body_temperature",
    "gl02ext__query_body_temperature_statistics",
    "imes__imes_relay_status",
    "imes__list_imes_database_profiles",
    "imes__list_imes_business_objects",
    "imes__search_imes_variables",
    "imes__explain_imes_variable",
    "imes__resolve_imes_natural_language",
    "imes__query_imes_object",
    "imes__query_imes_readonly_sql",
    "imes__query_imes_variables",
    "imes__query_hot_metal_silicon",
    "imes__get_current_heat_context",
    "imes__get_current_previous_heat_si_summary",
    "imes__resolve_spoken_heat_reference",
    "imes__query_hot_metal_chemistry_by_heat",
    "imes__query_heat_chemistry",
    "imes__query_current_heat_chemistry",
    "imes__query_heat_chemistry_by_time_range",
    "imes__query_blast_furnace_slag_by_heat",
    "imes__query_sinter_feed_chemistry",
    "imesweb__get_imes_web_status",
    "imesweb__list_imes_web_datasets",
    "imesweb__query_imes_web_dataset",
}


def _quoted_spans(text: str) -> list[str]:
    return [match.group(0) for match in _QUOTED_RE.finditer(text)]


def _instruction_text(text: str) -> str:
    return _QUOTED_RE.sub(" ", text)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _is_no_live_request(instruction: str) -> bool:
    return bool(_NO_LIVE_PATTERN.search(instruction) or _USER_DATA_PATTERN.search(instruction))


def _explicit_live_request(instruction: str) -> bool:
    if not _contains_any(instruction, _LIVE_TERMS):
        return False
    if qa_time_window_plan.temporal_intent(instruction):
        return True
    # Observational questions need data even without an imperative verb.
    # Require a current/window anchor and a reviewed object; generic process
    # explanations and quoted titles do not turn into live queries.
    if (re.search(r"当前|现在|目前|最近|过去", instruction)
            and re.search(r"大不大|高不高|低不低|稳不稳|顺不顺|偏高吗|偏低吗", instruction)
            and qa_entity_resolution.resolve_requested_entities(instruction).get("variables")
            and not _contains_any(instruction, ("通常", "一般", "原理", "原因", "含义"))):
        return True
    if _contains_any(instruction, _LIVE_ACTIONS):
        return True
    compact = re.sub(r"[\s，,。；;？?！!]", "", instruction)
    return len(compact) <= 12 and not _contains_any(instruction, _KNOWLEDGE_TERMS)


def build_task_plan(question: str) -> dict[str, Any]:
    """Return one auditable source plan for knowledge, history, reports and live data."""

    text = str(question or "").strip()
    quoted = _quoted_spans(text)
    instruction = _instruction_text(text).strip()
    entity_resolution = qa_entity_resolution.resolve_requested_entities(instruction)
    no_live = _is_no_live_request(instruction)
    wants_user_data = bool(_USER_DATA_PATTERN.search(instruction))
    book_reference = any(span.startswith("《") for span in quoted)
    wants_document = (_contains_any(instruction, _DOCUMENT_TERMS) or book_reference) and (
        _contains_any(instruction, _DOCUMENT_ACTIONS) or "按" in instruction or "根据" in instruction
    )
    wants_history = _contains_any(instruction, _HISTORY_TERMS)
    wants_report = _contains_any(instruction, _REPORT_TERMS)
    wants_live = _explicit_live_request(instruction) and not no_live
    if wants_document or wants_history or wants_report:
        explicit_compound_live = (
            _contains_any(instruction, ("当前", "现在", "实时", "再查", "同时查"))
            and _contains_any(instruction, _LIVE_ACTIONS)
        )
        wants_live = wants_live and explicit_compound_live

    intents: list[str] = []
    if wants_document:
        intents.append("document_knowledge")
    if wants_history:
        intents.append("conversation_history")
    if wants_report:
        intents.append("period_report")
    if wants_live:
        intents.append("live_data")
    if wants_user_data:
        intents.append("user_supplied_data")
    if not intents and _contains_any(instruction, _KNOWLEDGE_TERMS):
        intents.append("general_knowledge")
    if not intents:
        intents.append("ordinary_qa")

    primary = intents[0]
    allowed_sources: list[str] = []
    if "document_knowledge" in intents or "general_knowledge" in intents:
        allowed_sources.append("knowledge_base")
    if "conversation_history" in intents:
        allowed_sources.append("conversation_history")
    if "period_report" in intents:
        allowed_sources.append("period_report")
    if "live_data" in intents:
        allowed_sources.append("live_readonly_data")
    if "user_supplied_data" in intents:
        allowed_sources.append("user_message")

    allowed_tool_domains: list[str] = []
    if "conversation_history" in intents:
        allowed_tool_domains.append("conversation_history")
    if "period_report" in intents:
        allowed_tool_domains.append("period_report")
    if "live_data" in intents:
        allowed_tool_domains.append("live_readonly_data")

    search_knowledge = "document_knowledge" in intents or "general_knowledge" in intents
    allow_tools = bool(allowed_tool_domains)
    allow_prefetch = "live_data" in intents
    if no_live:
        allow_prefetch = False
        allow_tools = False
        allowed_tool_domains = []

    return {
        "schema": VERSION,
        "primary_intent": primary,
        "intents": intents,
        "instruction_text": instruction,
        "quoted_spans": quoted,
        "search_knowledge": search_knowledge,
        "allow_prefetch": allow_prefetch,
        "allow_mcp_tools": allow_tools,
        "allowed_sources": allowed_sources,
        "allowed_tool_domains": allowed_tool_domains,
        "entities": list(entity_resolution.get("variables") or []),
        "unresolved_entities": list(entity_resolution.get("unresolved") or []),
        "no_live_lookup": no_live,
        "reason": "+".join(intents),
    }


def public_task_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Return safe routing metadata without persisting raw question fragments."""

    source = dict(plan or {})
    return {
        "schema": source.get("schema") or VERSION,
        "primary_intent": source.get("primary_intent") or "ordinary_qa",
        "intents": list(source.get("intents") or []),
        "search_knowledge": bool(source.get("search_knowledge")),
        "allow_prefetch": bool(source.get("allow_prefetch")),
        "allow_mcp_tools": bool(source.get("allow_mcp_tools")),
        "allowed_sources": list(source.get("allowed_sources") or []),
        "allowed_tool_domains": list(source.get("allowed_tool_domains") or []),
        "entities": list(source.get("entities") or []),
        "unresolved_entity_count": len(source.get("unresolved_entities") or []),
        "no_live_lookup": bool(source.get("no_live_lookup")),
        "reason": str(source.get("reason") or ""),
        "quoted_span_count": len(source.get("quoted_spans") or []),
    }


def tool_domain(tool_name: str) -> str:
    """Map an exposed read-only tool to the evidence domain it can read."""

    name = str(tool_name or "").lower()
    if name in _HISTORY_TOOL_NAMES:
        return "conversation_history"
    if name in _REPORT_TOOL_NAMES:
        return "period_report"
    if name in _LIVE_READONLY_TOOL_NAMES:
        return "live_readonly_data"
    return "restricted_unknown"


def tool_allowed(tool_name: str, plan: dict[str, Any] | None) -> bool:
    allowed = set((plan or {}).get("allowed_tool_domains") or [])
    return tool_domain(tool_name) in allowed
