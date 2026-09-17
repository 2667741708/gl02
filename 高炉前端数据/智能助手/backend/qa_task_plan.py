"""Deterministic task planning before knowledge and tool routing.

REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916

The planner separates the user's instruction from quoted document text.  It is
pure and deliberately conservative: a source is enabled only when the outer
instruction needs it.  Model tool planning remains downstream of this gate.
"""
from __future__ import annotations

import re
import math
from typing import Any

import qa_entity_resolution
import qa_time_window_plan


VERSION = "qa-task-plan-v9-supplied-record-scope"

_QUOTED_RE = re.compile(r"“[^”]*”|‘[^’]*’|\"[^\"]*\"|'[^']*'|《[^》]*》")
_DOCUMENT_TERMS = (
    "三规二制", "原文", "全文", "制度", "规程", "手册",
    "文档", "条款", "章节", "操作规程", "安全规程", "技术规程",
)
_DOCUMENT_ACTIONS = ("说明", "解释", "摘要", "总结", "读取", "列出", "引用", "查找", "检索", "给出", "回答", "是什么", "有哪些", "核实", "确认", "验证")
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
    "查一下", "查下", "看一下", "画出来", "画出", "绘图", "可视化",
)
_KNOWLEDGE_TERMS = (
    "原理", "机理", "原因", "为什么", "含义", "解释", "工艺", "规则", "阈值",
    "依据", "知识", "如何", "怎么", "方案", "报警", "告警",
)
_NO_LIVE_PATTERN = re.compile(r"(?:不要|不需要|无需|不必|不用|禁止|不)\s*(?:查(?:询)?|读取|访问|调用|检索|连接)[^，。；;\n]{0,12}(?:实时|现场|生产|数据库|数据|工具)")
_USER_DATA_PATTERN = re.compile(
    r"(?:只|仅)(?:用|看|根据|依据|基于)(?:"
    r"[^，。；;\n]{0,16}(?:我给|我提供|这些数|假设|已给|提供的)"
    r"|\s*(?:下面|以下|这组|这份|这批|这些|上述|给定)[^，。；;\n]{0,8}(?:数据|数值|记录))"
)
_PROVIDED_DATA_PATTERN = re.compile(
    r"(?:我(?:给出|提供|给)的|(?:下面|以下)(?:是|为|的))[^，。；;\n：:]{0,12}(?:数据|数值)"
    r"|(?:这组|这些|这批|这份)[^，。；;\n：:]{0,12}(?:数据|数值)(?=\s*(?:是|为|[:：=]|[-+]?\d|[“\"\[]))"
)
_DECLARED_INPUT_PATTERN = re.compile(
    r"(?:假设|假定|假如|给定|已知|(?:^|请)设)[^，。；;\n]{0,48}(?:\d|数据|数值)"
)
_LITERAL_INPUT_PATTERN = re.compile(
    r"(?:数据|数值|温度|压力|风温|风量|压差)[^，。；;\n]{0,8}"
    r"(?:分别为|分别是|为|是)\s*[-+]?\d+(?:\.\d+)?"
)
_VALUE_CHANGE_INPUT_PATTERN = re.compile(
    r"(?:数据|数值|温度|压力|风温|风量|压差)[^，。；;\n]{0,8}"
    r"(?:从|由)\s*[-+]?\d+(?:\.\d+)?\s*"
    r"(?:千帕|兆帕|帕|摄氏度|华氏度|度|℃|℉|kpa|mpa|pa|%)?\s*"
    r"(?:升高|降低|提高|增加|减少|升|降|变)(?:到|至|为|成)\s*[-+]?\d+(?:\.\d+)?", re.I
)
_NUMERIC_VALUE_QUESTION = re.compile(
    r"(?:是否(?:是|为)|是不是)\s*[-+]?\d"
    r"|(?:是|为)\s*[-+]?\d+(?:\.\d+)?\s*"
    r"(?:千帕|兆帕|帕|摄氏度|华氏度|度|℃|℉|kpa|mpa|pa|%|百分比)?\s*[吗么][？?]?\s*$", re.I
)
_ALL_TOOLS_PATTERN = re.compile(
    r"(?:不要|不需要|无需|不必|不用|禁止|不)\s*"
    r"(?:(?:查(?:询)?|读取|访问|调用|检索|连接|使用|用)\s*)?"
    r"(?:(?:任何|所有|全部|外部|MCP)\s*)?(?:工具|数据库|数据)", re.I
)
_SOURCE_EXCLUSION_PREFIX = (
    r"(?:不要|不需要|无需|不必|不用|禁止|别|不允许|不能|不)\s*"
    r"(?:(?:查询|检索|读取|访问|调用|使用|引用|依据|结合|调取|获取|查看|查|看|读|用)\s*)?"
    r"(?:(?:任何|所有|全部|已有|这些|我的|我们的|正式|岗位|本地|历史)\s*)*"
)
_BOOK_SOURCE_ALIASES = ("冀钢炼铁三规二制", "三规二制", "高炉事故处理")
_SOURCE_ACTION_START = re.compile(
    r"(?:并且|以及|但是|同时|然后|不过|并|再|但|(?<!并)且)(?:"
    + "|".join(re.escape(action) for action in sorted(
        set(_DOCUMENT_ACTIONS + _LIVE_ACTIONS + ("按", "根据", "依据", "结合", "列出", "对比", "比较", "导出", "读一下")),
        key=len, reverse=True)) + ")"
)
_SOURCE_EXCLUSION_START = re.compile(
    _SOURCE_EXCLUSION_PREFIX + "(?:"
    + "|".join(re.escape(term) for term in _HISTORY_TERMS + _REPORT_TERMS + _DOCUMENT_TERMS + _BOOK_SOURCE_ALIASES + ("知识库",))
    + r"|《)"
)

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
    return bool(_NO_LIVE_PATTERN.search(instruction) or _ALL_TOOLS_PATTERN.search(instruction))


def lookup_constraints(question: str) -> dict[str, Any]:
    text = str(question or "")
    instruction = _instruction_text("；".join(active_source_clauses(text)))
    scope = user_data_scope(text)
    return {"no_live_lookup": _is_no_live_request(instruction) or scope["exclusive"]
            or (scope["present"] and not scope["live_clauses"]),
            "all_tools_disabled": bool(_ALL_TOOLS_PATTERN.search(instruction)
                                       or scope["exclusive"]),
            "source_exclusions": sorted(source_exclusion_domains(text)),
            "excluded_document_titles": sorted(excluded_document_titles(text))}


def instruction_clauses(text: str) -> list[str]:
    """Split outer instructions; preserve literal source titles and quotations."""
    stack, result, start = [], [], 0
    pairs = {"《": "》", "“": "”", "‘": "’", '"': '"', "'": "'"}
    for i, ch in enumerate(text):
        if stack and ch == stack[-1]:
            stack.pop()
        elif ch in pairs:
            stack.append(pairs[ch])
        elif not stack and ch in "，,；;。\n":
            if text[start:i].strip():
                result.append(text[start:i].strip())
            start = i + 1
        elif not stack and i > start and _SOURCE_ACTION_START.match(text, i):
            result.append(text[start:i].strip())
            start = i
        elif not stack and i > start and _SOURCE_EXCLUSION_START.match(text, i):
            result.append(text[start:i].strip())
            start = i
    if text[start:].strip():
        result.append(text[start:].strip())
    return result


def source_exclusion_domains(text: str) -> set[str]:
    """Read unqualified source prohibitions outside literal quotations."""
    instruction = _instruction_text(str(text or ""))
    groups = {"conversation_history": _HISTORY_TERMS,
              "period_report": _REPORT_TERMS,
              "knowledge_base": tuple(term for term in _DOCUMENT_TERMS if term not in _BOOK_SOURCE_ALIASES) + ("知识库",)}
    excluded = {domain for domain, terms in groups.items()
                if re.search(_SOURCE_EXCLUSION_PREFIX + "(?:" + "|".join(re.escape(term) for term in terms) + ")", instruction)}
    return excluded


def excluded_document_titles(text: str) -> set[str]:
    """An excluded named book does not exclude another document source."""
    titles = set()
    book_pattern = "(?:" + "|".join(re.escape(alias) for alias in sorted(_BOOK_SOURCE_ALIASES, key=len, reverse=True)) + ")"
    for clause in instruction_clauses(str(text or "")):
        matches = [match for match in _QUOTED_RE.finditer(clause) if match.group(0).startswith("《")]
        if any(re.search(_SOURCE_EXCLUSION_PREFIX + r"$", _instruction_text(clause[:match.start()])) for match in matches):
            titles.update(match.group(0)[1:-1].strip() for match in matches)
        for match in re.finditer(_SOURCE_EXCLUSION_PREFIX + "(" + book_pattern + r"(?:\s*(?:和|与|及|、)\s*" + book_pattern + ")*)", _instruction_text(clause)):
            titles.update(re.findall(book_pattern, match.group(1)))
    return titles


def active_source_clauses(text: str) -> list[str]:
    return [clause for clause in instruction_clauses(str(text or ""))
            if not source_exclusion_domains(clause) and not excluded_document_titles(clause)]


def apply_source_exclusions(plan: dict[str, Any], exclusions, document_titles=None) -> dict[str, Any]:
    """Carry parent prohibitions through independently rebuilt child plans."""
    result = dict(plan)
    excluded = set(result.get("source_exclusions") or []) | set(exclusions or [])
    result["source_exclusions"] = sorted(excluded)
    titles = set(result.get("excluded_document_titles") or []) | set(document_titles or [])
    result["excluded_document_titles"] = sorted(titles)
    result["document_lookup_disabled"] = "knowledge_base" in excluded
    result["allowed_sources"] = [source for source in result.get("allowed_sources", []) if source not in excluded]
    result["allowed_tool_domains"] = [domain for domain in result.get("allowed_tool_domains", []) if domain not in excluded]
    result["allow_mcp_tools"] = bool(result.get("allow_mcp_tools") and result["allowed_tool_domains"])
    # Unfiltered keyword retrieval cannot enforce an excluded book binding.
    # Explicit document readers enforce the precise source identity instead.
    if "knowledge_base" in excluded or titles:
        result["search_knowledge"] = False
    return result


def _conceptual_source_clause(clause: str) -> bool:
    """Explaining a record domain is not a request to read stored records."""
    instruction = _instruction_text(clause)
    if not _contains_any(instruction, _HISTORY_TERMS + _REPORT_TERMS):
        return False
    # Explicit sources, scoped records and read commands retain their original
    # evidence domain, even when the question also asks about their meaning.
    if (_quoted_spans(clause) or _contains_any(instruction, _DOCUMENT_TERMS)
            or re.search(r"查询|查一下|查下|检索|读取|调取|获取|查看|列出|导出|生成", instruction)
            or re.search(r"今天|今日|昨天|昨日|前天|最近|过去|当前|现在|最新|实时|之前|此前|上一|上次|我的|我们的|我(?:问|说)|这[份篇条次本]|这个(?!概念)|该[份篇条次本]|那[份篇个条次本]|\d{4}[年/.-]\d{1,2}|\d{1,2}月\d{1,2}日|\d{1,2}[点时]|[Ii][Dd]\s*[:：=]", instruction)
            or re.search(r"(?:日报|周报|月报|报表|生产报告|聊天记录|对话记录|历史问答|历史会话)[^，。；;\n]{0,4}(?:里|中|第\d)", instruction)):
        return False
    return bool(re.search(
        r"区别|差别|用途|作用|原理|概念|定义|含义|什么意思"
        r"|(?:如何|怎么)(?:编写|写)"
        r"|(?:一般|通常)[^，。；;\n]{0,8}(?:包括|包含)"
        r"|(?:日报|周报|月报|报表|生产报告|聊天记录|对话记录|历史问答|历史会话)\s*是什么",
        instruction))


def user_data_scope(text: str) -> dict[str, Any]:
    """Keep supplied inputs distinct from explicitly requested external reads."""
    instruction = _instruction_text(str(text or ""))
    present = any(_declared_input_clause(clause) for clause in instruction_clauses(str(text or "")))
    live_clauses = []
    external_source_requested = False
    global_exclusive = any(
        re.search(r"(?:本轮|全程|整个回答|所有子任务|全部问题)\s*$", instruction[max(0, match.start() - 12):match.start()])
        for match in _USER_DATA_PATTERN.finditer(instruction)
    )
    if present:
        for clause in instruction_clauses(str(text or "")):
            masked = _instruction_text(clause)
            if _declared_input_clause(clause):
                continue
            if _conceptual_source_clause(clause):
                continue
            if source_exclusion_domains(clause) or excluded_document_titles(clause):
                continue
            if (any(span.startswith("《") for span in _quoted_spans(clause))
                    or _contains_any(masked, _DOCUMENT_TERMS + _HISTORY_TERMS + _REPORT_TERMS)):
                if _contains_any(masked, _DOCUMENT_ACTIONS + _LIVE_ACTIONS + ("列出", "导出")):
                    external_source_requested = True
                continue
            # A later request to query/plot "these data" refers to supplied
            # inputs, unless it explicitly names an external source.
            if (re.search(r"(?:这些|这组|上述|给定|提供的)[^，。；;\n]{0,8}(?:数据|数值)", masked)
                    and not re.search(r"现场|数据库|实测|传感器|实时接口|生产系统", masked)):
                continue
            read_requested = re.search(r"查询|查一下|查下|读取|调取|检索|获取|查看|看一下|看看", masked)
            current_value_requested = (re.search(r"当前|现在|目前|最新|实时", masked)
                                       and re.search(r"是多少|多少|高不高|低不低|稳不稳", masked))
            if (read_requested or current_value_requested) and _explicit_live_request(masked):
                live_clauses.append(masked)
                external_source_requested = True
    exclusive = global_exclusive or (bool(_USER_DATA_PATTERN.search(instruction)) and not external_source_requested)
    return {"present": present, "live_clauses": live_clauses, "exclusive": bool(exclusive)}


def _declared_input_clause(clause: str) -> bool:
    """A literal assertion is an input; a query or quoted clause is not."""
    instruction = _instruction_text(clause)
    if _USER_DATA_PATTERN.search(instruction):
        return True
    if _PROVIDED_DATA_PATTERN.search(instruction):
        source_named = (_contains_any(instruction, _DOCUMENT_TERMS + _HISTORY_TERMS + _REPORT_TERMS)
                        or any(span.startswith("《") for span in _quoted_spans(clause)))
        outer_read = re.match(r"\s*(?:请|请先|帮我|麻烦)?\s*(?:查询|查看|读取|调取|检索|查一下|查下|获取)", instruction)
        source_verification = (re.match(r"\s*(?:请|请先|帮我|麻烦)?\s*(?:核实|确认|验证)", instruction)
                               and re.search(r"与|和|核对|一致|相符|真实|正式原文|现场|数据库|生产系统|实时接口", instruction))
        # Referring to provided inputs while requesting source verification is
        # not an assertion that the verified external records were supplied.
        if source_named and (outer_read or source_verification):
            return False
        return True
    if (any(span.startswith("《") for span in _quoted_spans(clause))
            or _contains_any(instruction, _DOCUMENT_TERMS + _HISTORY_TERMS + _REPORT_TERMS)
            or re.search(r"查询|查看|读取|调取|检索|查一下|查下|获取|核实|确认|验证", instruction)
            or _NUMERIC_VALUE_QUESTION.search(instruction)):
        return False
    if _DECLARED_INPUT_PATTERN.search(instruction):
        return True
    for pattern in (_LITERAL_INPUT_PATTERN, _VALUE_CHANGE_INPUT_PATTERN):
        for match in pattern.finditer(instruction):
            suffix = instruction[match.end():].lstrip()
            if not re.match(r"[年月日点时]|[:：]\d|[/-]\d{1,2}[/-]\d", suffix):
                return True
    return False


def live_query_text(question: str) -> str:
    text = str(question or "")
    scope = user_data_scope(text)
    if not scope["present"]:
        return "；".join(active_source_clauses(text))
    if lookup_constraints(text)["no_live_lookup"]:
        return ""
    return "；".join(scope["live_clauses"])


def _independent_temporal_data_task(text: str) -> bool:
    for clause in instruction_clauses(text):
        instruction = _instruction_text(clause)
        if (any(span.startswith("《") for span in _quoted_spans(clause))
                or _contains_any(instruction, _DOCUMENT_TERMS + _HISTORY_TERMS + _REPORT_TERMS)):
            continue
        anchored = bool(re.search(r"今天|今日|昨天|昨日|前天|最近|过去|\d{4}[年/.-]\d{1,2}[月/.-]\d{1,2}|\d{1,2}月\d{1,2}日", instruction)
                        or qa_time_window_plan.explicit_clock_intent(instruction)
                        or qa_time_window_plan.temporal_intent(instruction))
        if (anchored and _contains_any(instruction, _LIVE_ACTIONS + ("对比", "比较"))
                and _explicit_live_request(instruction)):
            return True
    return False


def _explicit_live_request(instruction: str) -> bool:
    if not _contains_any(instruction, _LIVE_TERMS):
        return False
    if (not re.search(r"当前|现在|目前|最近|过去|今天|今日|昨天|最新|实时", instruction)
            and _contains_any(instruction, ("通常", "一般", "原理", "原因", "含义"))):
        return False
    if qa_time_window_plan.temporal_intent(instruction):
        return True
    # Numeric yes/no questions ask to verify a current measurement; do not
    # treat their candidate value as a supplied measurement to reason from.
    if re.search(r"当前|现在|目前|最新|实时", instruction) and _NUMERIC_VALUE_QUESTION.search(instruction):
        return True
    # REQ-QA-EXPLICIT-CLOCK-AND-CHART-20260917: route requests even when
    # their explicit clock is invalid; the execution preflight clarifies it.
    if (qa_time_window_plan.explicit_clock_intent(instruction)
            and _contains_any(instruction, _LIVE_ACTIONS)):
        return True
    # REQ-QA-SINGLE-WINDOW-OBSERVATION-20260917
    # Single-window comparisons and stability questions are observations too.
    # The downstream reviewed resolver owns exact point IDs; requiring its
    # separate multi-entity range resolver here drops valid single body points.
    if (re.search(r"当前|现在|目前|最近|过去", instruction)
            and re.search(r"对比|比较|稳不稳|大不大|高不高|低不低|顺不顺|偏高吗|偏低吗", instruction)
            and re.search(r"压差|炉体温度|炉顶压力|顶压|炉喉温度|铁口温度|风量|风温|(?:第)?\d{1,2}层\s*[A-Fa-f]\s*温度", instruction)
            and not _contains_any(instruction, ("通常", "一般", "原理", "原因", "含义", "假设"))):
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
    # A source label on an input declaration is provenance supplied by the
    # user, not an instruction to read that source. Independent source clauses
    # retain their authority and gates; declared values remain in the message.
    active_clauses = [clause for clause in active_source_clauses(text)
                      if not _declared_input_clause(clause)]
    quoted = _quoted_spans("；".join(active_clauses))
    instruction = _instruction_text("；".join(active_clauses)).strip()
    user_scope = user_data_scope(text)
    live_instruction = "；".join(user_scope["live_clauses"]) if user_scope["present"] else instruction
    entity_resolution = qa_entity_resolution.resolve_requested_entities(live_instruction)
    constraints = lookup_constraints(text)
    no_live = constraints["no_live_lookup"]
    wants_user_data = user_scope["present"]
    book_reference = any(span.startswith("《") for span in quoted)
    wants_document = (_contains_any(instruction, _DOCUMENT_TERMS) or book_reference) and (
        _contains_any(instruction, _DOCUMENT_ACTIONS) or "按" in instruction or "根据" in instruction or "依据" in instruction
    )
    source_clauses = [_instruction_text(clause) for clause in active_clauses
                      if not _conceptual_source_clause(clause)]
    wants_history = any(_contains_any(clause, _HISTORY_TERMS) for clause in source_clauses)
    wants_report = any(_contains_any(clause, _REPORT_TERMS) for clause in source_clauses)
    wants_live = _explicit_live_request(instruction) and not no_live
    if wants_document or wants_history or wants_report:
        explicit_compound_live = (
            _contains_any(instruction, ("当前", "现在", "实时", "再查", "同时查"))
            and _contains_any(instruction, _LIVE_ACTIONS)
        )
        wants_live = wants_live and (explicit_compound_live or _independent_temporal_data_task(text))

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
    if constraints["all_tools_disabled"]:
        allow_tools = False
        allowed_tool_domains = []
        search_knowledge = False
        allowed_sources = [source for source in allowed_sources if source == "user_message"]

    return apply_source_exclusions({
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
        "all_tools_disabled": constraints["all_tools_disabled"],
        "reason": "+".join(intents),
    }, constraints["source_exclusions"], constraints["excluded_document_titles"])


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
        "all_tools_disabled": bool(source.get("all_tools_disabled")),
        "source_exclusions": list(source.get("source_exclusions") or []),
        "document_lookup_disabled": bool(source.get("document_lookup_disabled")),
        "excluded_document_count": len(source.get("excluded_document_titles") or []),
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


def sensor_context_policy(plan: dict[str, Any] | None, *, code_only: bool = False) -> dict[str, Any]:
    """Preparation may read sensors only under an explicit live source grant."""
    source = plan if isinstance(plan, dict) else {}
    if code_only:
        enabled, reason = False, 'disabled_code_only'
    elif source.get('no_live_lookup') or source.get('all_tools_disabled'):
        enabled, reason = False, 'explicit_source_restriction'
    else:
        intents, sources = source.get('intents'), source.get('allowed_sources')
        enabled = (isinstance(intents, list) and 'live_data' in intents
            and isinstance(sources, list) and 'live_readonly_data' in sources
            and source.get('allow_prefetch') is True)
        reason = 'task_plan_live_source_granted' if enabled else 'task_plan_has_no_live_source_grant'
    return {'schema': 'qa-sensor-context-source-gate-v2', 'enabled': bool(enabled),
        'skipped': not enabled, 'reason': reason}


def bound_rule_context_requested(question: str, plan: dict[str, Any] | None = None) -> bool:
    """A bound rule is evidence only for an active request about that rule."""
    source = plan if isinstance(plan, dict) else build_task_plan(question)
    if set(source.get('intents') or []) & {'user_supplied_data', 'document_knowledge',
            'conversation_history', 'period_report'}:
        return False
    instruction = _instruction_text('；'.join(active_source_clauses(str(question or ''))))
    if re.search(r'换个话题|新问题|另一个问题|不要继承|忘掉', instruction):
        return False
    if re.search(r'(?:不要|禁止|不使用|不引用|不用|无需)[^；。]{0,12}(?:绑定|本对话|本会话|ABC)[^；。]{0,8}上下文', instruction):
        return False
    return bool(re.search(
        r'(?:本对话|本会话|此对话|此会话)[^；。]{0,20}(?:规则|评分|公式|权重|归一化|上下文)'
        r'|(?:绑定的?|这个|这条|这项|那个|那条|那项|上述|刚才)[^；。]{0,8}(?:规则|评分|公式|得分|权重|归一化)'
        r'|(?<![A-Za-z0-9_])(?:A[1-9]|B(?:1[0-3]|[1-9])|C(?:1[01]|[1-9]))(?![A-Za-z0-9_])[^；。]{0,12}(?:规则|评分|得分|分数|触发|公式|权重|归一化)',
        instruction))


def resolve_owned_followup(question: str, plan: dict[str, Any], context: dict[str, Any],
        known_objects: list[str], *, code_only: bool = False) -> dict[str, Any]:
    """Resolve a referential read from server-loaded owned ancestry, never old values.

    The caller must load context with load_owned_tool_context and update its
    active instruction first. This pure resolver does not authenticate a client.
    """
    result = {'task_plan': dict(plan), 'state': 'not_applicable', 'outcome': None}
    if code_only:
        disabled = dict(plan)
        disabled.update(allow_prefetch=False, allow_mcp_tools=False, search_knowledge=False,
            allowed_sources=[], allowed_tool_domains=[], reason='disabled_code_only')
        result.update(task_plan=disabled,state='disabled_code_only')
        return result
    if plan.get('no_live_lookup') or plan.get('all_tools_disabled'):
        return result
    if set(plan.get('intents') or []) & {'user_supplied_data', 'document_knowledge',
            'conversation_history', 'period_report'}:
        return result
    if 'live_readonly_data' in (plan.get('source_exclusions') or []):
        return result
    if '[服务端对话状态：' in str(question or ''):
        return result
    if (sensor_context_policy(plan)['enabled'] and plan.get('allow_mcp_tools') is True
            and bool(plan.get('entities'))):
        result['state'] = 'already_explicit_live'
        return result
    instruction = str(plan.get('instruction_text') or '')
    if bound_rule_context_requested(question, plan):
        return result
    if not re.match(r'^\s*(?:刚才|上面|那个|这个|它们?|这些|上述变量|继续|再看|画出来|画一下|来张图|换成|改成|换散点)', instruction):
        return result
    if re.search(r'换个话题|新问题|另一个问题|不要继承|忘掉|原理|通常|一般|概念|含义|翻译|代码|脚本|密码|凭据|连接串|删除|写入|更新数据库', instruction):
        return result
    goal = context.get('analysis_goal')
    if goal not in {'latest', 'history', 'statistics', 'correlation', 'plot'}:
        return result
    if not re.search(r'趋势|走势|波动|变化|最近|过去|现在|当前|最新|多少|平均|统计|最高|最低|画|图|比较|对比|相关|继续', instruction):
        return result
    objects = context.get('selected_objects')
    inheritance = context.get('inheritance')
    provenance = context.get('inheritance_provenance')
    object_provenance = provenance.get('objects') if isinstance(provenance, dict) else None
    sources = object_provenance.get('sources') if isinstance(object_provenance, dict) else None
    valid_objects = (isinstance(objects, list) and bool(objects)
        and all(isinstance(name, str) and name and name in known_objects for name in objects)
        and len(set(objects)) == len(objects))
    owned_sources = (valid_objects and isinstance(sources, dict) and set(sources) == set(objects)
        and all(type(sources[name]) is int and sources[name] > 0 for name in objects))
    valid_inheritance = (isinstance(inheritance, dict) and inheritance.get('objects') is True
        and context.get('inheritance_reason') == 'explicit_followup'
        and context.get('pending_clarification') is None)
    if not (owned_sources and valid_inheritance):
        clarification_plan = dict(plan)
        clarification_plan.update(allow_prefetch=False, allow_mcp_tools=False,
            search_knowledge=False, allowed_sources=[], allowed_tool_domains=[],
            reason='owned_followup_needs_clarification')
        result['task_plan'] = clarification_plan
        result['state'] = 'needs_clarification'
        result['outcome'] = {'ok': True, 'tool_used': False,
            'answer': '请明确要查看哪个数据对象或测点；此前对象缺失、过期或无法核验，本次未查询现场数据，也未沿用旧数值。',
            'answer_route': 'owned_followup_needs_clarification',
            'answer_contract': 'needs_clarification', 'needs_clarification': True}
        return result
    resolved = dict(plan)
    resolved.update(primary_intent='live_data', intents=['live_data'], search_knowledge=False,
        allow_prefetch=True, allow_mcp_tools=True, allowed_sources=['live_readonly_data'],
        allowed_tool_domains=['live_readonly_data'], entities=list(objects), unresolved_entities=[],
        reason='owned_referential_followup')
    result.update(task_plan=resolved, state='owned_live_followup')
    return result


def pending_data_object_context(context: dict[str, Any], resolution: dict[str, Any]) -> dict[str, Any]:
    """Record only a deterministic data-object clarification, never a model guess."""
    result = dict(context)
    result.pop('pending_data_object', None)
    if resolution.get('state') != 'needs_clarification':
        return result
    goal = context.get('analysis_goal')
    stamp = context.get('updated_at')
    window = context.get('time_range')
    chart = context.get('preferred_chart')
    if (goal not in {'latest', 'history', 'statistics', 'correlation', 'plot'}
            or type(stamp) not in (int, float) or not math.isfinite(stamp)):
        return result
    if window is not None and (not isinstance(window, dict) or set(window) != {'mode', 'minutes'}
            or window.get('mode') != 'relative' or type(window.get('minutes')) is not int
            or not 1 <= window['minutes'] <= 1440):
        return result
    if chart not in {None, 'trend', 'correlation_heatmap', 'matrix', 'correlation_scatter', 'boxplot', 'distribution'}:
        return result
    result['selected_objects'] = []
    result['last_evidence'] = []
    result['evidence_reuse'] = False
    result['pending_data_object'] = {'schema': 'qa.pending-data-object.v1',
        'goal': goal, 'time_range': dict(window) if window else None,
        'preferred_chart': chart, 'requested_at': stamp}
    return result


def resolve_pending_data_object(question: str, plan: dict[str, Any], previous: dict[str, Any] | None,
        alias_registry: tuple[tuple[str, tuple[str, ...]], ...], *, now: float,
        code_only: bool = False) -> dict[str, Any]:
    """Resume an exact object confirmation from a server-loaded owned user turn.

    The caller must use load_owned_tool_context. A positive integer supplied by
    a client is not authentication; no client context may reach this resolver.
    The generated question is internal. The original user message stays intact.
    """
    result = {'state': 'not_applicable', 'task_plan': dict(plan),
        'execution_question': question, 'outcome': None, 'pending_context': None}
    if (code_only or plan.get('no_live_lookup') or plan.get('all_tools_disabled')
            or set(plan.get('intents') or []) & {'user_supplied_data', 'document_knowledge',
                'conversation_history', 'period_report'}
            or 'live_readonly_data' in (plan.get('source_exclusions') or [])
            or bound_rule_context_requested(question, plan)):
        return result
    labels: dict[str, set[str]] = {}
    for name, aliases in alias_registry:
        for label in (name, *aliases):
            labels.setdefault(label.strip().casefold(), set()).add(name)
    text = str(question or '').strip().rstrip('。.!！?？').strip()
    prefix = re.match(r'^(?:我指的是|我说的是|测点是|变量是|就是|是)\s*', text)
    if prefix:
        text = text[prefix.end():].strip()
    objects = []
    for part in re.split(r'\s*(?:、|，|,|和|与|&)\s*', text):
        part = part.strip()
        if len(part) >= 2 and (part[0], part[-1]) in {('“', '”'), ('"', '"'), ('‘', '’'), ("'", "'")}:
            part = part[1:-1].strip()
        matches = labels.get(part.casefold(), set())
        if len(matches) != 1:
            return result
        objects.append(next(iter(matches)))
    if not objects or len(set(objects)) != len(objects):
        return result
    # A bare label is not an independent live-query authorization. Authenticate
    # its pending task before granting any read, including preparation reads.
    closed = dict(plan)
    closed.update(allow_prefetch=False, allow_mcp_tools=False, search_knowledge=False,
        allowed_sources=[], allowed_tool_domains=[], reason='owned_followup_needs_clarification')
    result.update(state='needs_clarification', task_plan=closed,
        outcome={'ok': True, 'tool_used': False,
            'answer': '请明确查询目标和时间范围；待确认任务缺失、过期或无法核验，本次未查询现场数据。',
            'answer_route': 'owned_followup_needs_clarification', 'answer_contract': 'needs_clarification', 'needs_clarification': True})
    previous = previous if isinstance(previous, dict) else {}
    pending = previous.get('pending_data_object')
    if (not isinstance(pending, dict) or set(pending) != {'schema', 'goal', 'time_range', 'preferred_chart', 'requested_at'}
            or pending.get('schema') != 'qa.pending-data-object.v1'
            or type(previous.get('source_message_id')) is not int or previous['source_message_id'] <= 0):
        return result
    stamp = pending.get('requested_at')
    if (type(now) not in (int, float) or not math.isfinite(now)
            or type(stamp) not in (int, float) or not math.isfinite(stamp)
            or type(previous.get('updated_at')) not in (int, float) or not math.isfinite(previous['updated_at'])
            or previous.get('updated_at') != stamp or not 0 <= now - stamp <= 600):
        return result
    goal, window, chart = pending.get('goal'), pending.get('time_range'), pending.get('preferred_chart')
    if (goal not in {'latest', 'history', 'statistics', 'correlation', 'plot'}
            or goal != previous.get('analysis_goal') or window != previous.get('time_range')
            or chart != previous.get('preferred_chart')):
        return result
    if window is not None and (not isinstance(window, dict) or set(window) != {'mode', 'minutes'}
            or window.get('mode') != 'relative' or type(window.get('minutes')) is not int
            or not 1 <= window['minutes'] <= 1440):
        return result
    if chart not in {None, 'trend', 'correlation_heatmap', 'matrix', 'correlation_scatter', 'boxplot', 'distribution'}:
        return result
    if goal == 'correlation' and len(objects) < 2:
        closed = dict(plan)
        closed.update(allow_prefetch=False, allow_mcp_tools=False, search_knowledge=False,
            allowed_sources=[], allowed_tool_domains=[], reason='owned_followup_needs_clarification')
        result.update(state='needs_clarification', task_plan=closed,
            pending_context={'analysis_goal': goal, 'time_range': dict(window) if window else None,
                'preferred_chart': chart, 'updated_at': stamp},
            outcome={'ok': True, 'tool_used': False, 'answer': '相关性分析需要至少两个明确测点，请一起列出；本次未查询现场数据。',
                'answer_route': 'owned_followup_needs_clarification', 'answer_contract': 'needs_clarification', 'needs_clarification': True})
        return result
    action = {'latest': '查询最新值', 'history': '查询历史趋势', 'statistics': '查询历史统计',
        'correlation': '查询相关性', 'plot': '画趋势图'}[goal]
    chart_text = {None: '', 'trend': '趋势图', 'correlation_heatmap': '相关热力图', 'matrix': '矩阵图',
        'correlation_scatter': '散点图', 'boxplot': '箱线图', 'distribution': '直方图'}[chart]
    execution = ' '.join([action, '、'.join(objects),
        '最近' + str(window['minutes']) + '分钟' if window else '', chart_text]).strip()
    resolved = build_task_plan(execution)
    resolved.update(primary_intent='live_data', intents=['live_data'], search_knowledge=False,
        allow_prefetch=True, allow_mcp_tools=True, allowed_sources=['live_readonly_data'],
        allowed_tool_domains=['live_readonly_data'], entities=objects, unresolved_entities=[],
        reason='owned_referential_followup')
    result.update(state='confirmed_data_object', task_plan=resolved, execution_question=execution, outcome=None)
    return result
