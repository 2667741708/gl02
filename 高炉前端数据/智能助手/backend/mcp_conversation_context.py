"""Structured conversation state for contextual MCP follow-up questions.

The state is intentionally compact and contains only business object IDs,
relative time, analysis intent and chart preference. It never stores database
credentials, SQL, full furnace snapshots or model prompts.

Requirement: REQ-MCP-CONVERSATION-CONTEXT-20260726
"""
from __future__ import annotations

from typing import Any
import math
import re
import time


FOLLOWUP_TERMS = (
    "刚才",
    "上面",
    "那个",
    "这个",
    "它",
    "它们",
    "这些",
    "再",
    "继续",
    "换",
    "换成",
    "改成",
    "画出来",
    "一张图",
    "来张图",
    "画一下",
    "画一个",
    "看趋势",
    "走势呢",
    "也画",
    "也加",
    "也看",
    "一起",
)
ADD_TERMS = ("再加", "加上", "也加", "也看", "再看", "一起看", "同时")


def empty_tool_context() -> dict[str, Any]:
    return {
        "version": 2,
        "selected_objects": [],
        "time_range": None,
        "analysis_goal": None,
        "preferred_chart": None,
        "last_tool_names": [],
        "last_evidence": [],
        "pending_clarification": None,
        "inheritance": {"objects": False, "time_range": False},
    }


def infer_analysis_goal(question: str) -> str | None:
    text = str(question or "")
    if any(term in text for term in ("相关", "关系", "关联", "同步", "比较", "对比")):
        return "correlation"
    if any(term in text for term in ("画", "图", "曲线", "可视化")):
        return "plot"
    if any(term in text for term in ("平均", "最高", "最低", "统计", "波动", "稳不稳")):
        return "statistics"
    if any(term in text for term in ("历史", "趋势", "走势", "变化", "最近", "过去", "近")):
        return "history"
    if any(term in text for term in ("现在", "当前", "最新", "多少", "是多少")):
        return "latest"
    return None


def infer_chart(question: str, analysis_goal: str | None) -> str | None:
    text = str(question or "")
    if any(term in text for term in ("相关矩阵", "相关热力图")):
        return "correlation_heatmap"
    if "热力" in text or "矩阵" in text:
        return "matrix"
    if any(term in text for term in ("相关", "散点", "关系图")):
        return "correlation_scatter"
    if any(term in text for term in ("箱线", "箱型", "盒须")):
        return "boxplot"
    if any(term in text for term in ("分布", "直方")):
        return "distribution"
    if analysis_goal == "plot" or any(term in text for term in ("曲线", "趋势图", "走势")):
        return "trend"
    return None


def update_tool_context(
    previous: dict[str, Any] | None,
    question: str,
    detected_objects: list[str] | None = None,
    duration_minutes: int | None = None,
    *, now: float | None = None,
) -> dict[str, Any]:
    """Merge explicit objects/time with safe follow-up inheritance."""

    previous = previous if isinstance(previous, dict) else {}
    context = empty_tool_context()
    previous_objects = [str(value) for value in previous.get("selected_objects") or [] if str(value)]
    detected = list(dict.fromkeys(str(value) for value in detected_objects or [] if str(value)))
    text = str(question or "")
    current_time = time.time() if now is None else now
    previous_time = previous.get("updated_at")
    valid_clock = (not isinstance(previous_time, bool) and isinstance(previous_time, (int, float))
                   and math.isfinite(previous_time))
    has_prior_scope = bool(previous_objects or previous.get('time_range'))
    unverified_clock = has_prior_scope and not valid_clock
    stale = unverified_clock or (valid_clock and (current_time - previous_time > 600 or current_time < previous_time))
    reset = bool(re.search(r"换个话题|新问题|另一个问题|不看(?:刚才|上面|之前)|忘掉|不要继承", text)
                 or re.search(r"(?:不要|不需要|无需|不必|禁止|不)[^，。；;\n]{0,16}(?:查询|查实时|访问|调用)[^，。；;\n]{0,12}(?:数据|工具|现场|数据库)", text)
                 or re.search(r"原理|一般|通常|概念|含义|制度|规程|历史问答|聊天记录", text))
    starts_with_link = text.lstrip().startswith(("和", "与")) and not reset
    # Short connective characters inside a new topic (例如“再次解释制度”) are
    # insufficient to inherit sensor objects or a historical query window.
    is_followup = (starts_with_link or bool(re.match(r"\s*(?:刚才|上面|那个|这个|它们?|这些|继续|再看|再加|加上|也看|也加|一起看|同时看|换成|改成|换散点|画出来|一张图|来张图|画一下|画一个|看趋势|走势呢)", text))) and not reset and not stale
    should_add = is_followup and (starts_with_link or bool(re.match(r"\s*(?:再加|加上|也加|也看|再看|一起看|同时看)", text)))
    if detected and previous_objects and set(detected).isdisjoint(previous_objects) and not should_add:
        is_followup = False
    if stale or reset:
        previous_objects = []

    if detected and should_add and previous_objects:
        selected = list(dict.fromkeys([*previous_objects, *detected]))
        inherited_objects = True
    elif detected:
        selected = detected
        inherited_objects = False
    elif is_followup:
        selected = previous_objects
        inherited_objects = bool(previous_objects)
    else:
        selected = []
        inherited_objects = False

    explicit_duration = isinstance(duration_minutes, int) and not isinstance(duration_minutes, bool) and duration_minutes > 0
    current_read = (not explicit_duration and bool(re.search(r'现在|当前|最新|实时|此刻|目前', text))
                    and not re.search(r'趋势|统计|平均|最高|最低|波动|过去|最近|历史|对比|比较', text))
    previous_range = previous.get('time_range')
    prior_minutes = previous_range.get('minutes') if isinstance(previous_range, dict) else None
    valid_prior_range = (isinstance(previous_range, dict) and previous_range.get('mode') == 'relative'
                         and isinstance(prior_minutes, int) and not isinstance(prior_minutes, bool) and prior_minutes > 0)
    if explicit_duration:
        time_range = {"mode": "relative", "minutes": int(duration_minutes)}
        inherited_time = False
    elif is_followup and valid_prior_range and not current_read:
        time_range = {"mode": "relative", "minutes": prior_minutes}
        inherited_time = True
    else:
        time_range = None
        inherited_time = False

    goal = 'latest' if current_read else infer_analysis_goal(text)
    if not goal and is_followup:
        goal = previous.get("analysis_goal")
    chart = infer_chart(text, goal)
    if not chart and is_followup and goal == previous.get("analysis_goal"):
        chart = previous.get("preferred_chart")

    context.update(
        {
            "selected_objects": selected,
            "time_range": time_range,
            "analysis_goal": goal,
            "preferred_chart": chart,
            "last_tool_names": [],
            "last_evidence": [],
            "pending_clarification": "missing_business_object" if goal and not selected else None,
            "inheritance": {"objects": inherited_objects, "time_range": inherited_time},
            "updated_at": current_time,
            "inheritance_reason": "clock_unverified" if unverified_clock else "expired" if stale else "explicit_reset" if reset else "explicit_followup" if is_followup else "new_question",
            "inheritance_provenance": {
                "objects": {"source_updated_at": previous_time if inherited_objects else current_time,
                            "basis": "explicit_followup" if inherited_objects else "explicit_objects" if selected else "none"},
                "time_range": {"source_updated_at": previous_time if inherited_time else current_time if time_range else None,
                               "basis": "explicit_followup" if inherited_time else "explicit_duration" if time_range else "explicit_latest_reset" if current_read else "none"},
            },
            "evidence_reuse": False,
        }
    )
    return context


def enrich_routing_question(question: str, context: dict[str, Any] | None) -> str:
    """Add a private deterministic-routing suffix; never show it to the user."""

    context = context or {}
    objects = list(context.get("selected_objects") or [])
    time_range = context.get("time_range") if isinstance(context.get("time_range"), dict) else {}
    if not objects:
        return str(question or "")
    suffix = [f"标准变量：{', '.join(objects)}"]
    minutes = time_range.get("minutes")
    if minutes:
        suffix.append(f"最近{int(minutes)}分钟")
    goal = context.get("analysis_goal")
    if goal:
        suffix.append(f"查询意图：{goal}")
    chart = context.get("preferred_chart")
    if chart:
        suffix.append(f"图表类型：{chart}")
    suffix.append(
        {
            "latest": "查询最新值",
            "history": "查询历史趋势",
            "statistics": "查询历史统计",
            "correlation": "分析相关性",
            "plot": "绘制趋势图",
        }.get(str(goal), "执行数据查询")
    )
    return f"{question}\n[服务端对话状态：{'；'.join(suffix)}]"


def context_with_tool_trace(
    context: dict[str, Any] | None,
    tool_trace: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Persist compact tool/evidence references after execution."""

    result = dict(context or empty_tool_context())
    names: list[str] = []
    evidence: list[dict[str, Any]] = []
    for item in tool_trace or []:
        name = str(item.get("tool") or "")
        if name:
            names.append(name)
        payload = item.get("result")
        if isinstance(payload, dict):
            evidence_item = {
                "tool": name,
                "server_id": item.get("server_id"),
                "image_url": payload.get("image_url"),
                "count": payload.get("count") or payload.get("success_count") or payload.get("sample_count"),
                "object_id": ((payload.get("object") or {}).get("object_id") if isinstance(payload.get("object"), dict) else None),
                "current_heat_no": payload.get("current_heat_no"),
                "previous_heat_no": payload.get("previous_heat_no"),
                "as_of_time": payload.get("as_of_time"),
                "heat_time_window": payload.get("heat_time_window"),
            }
            evidence.append({key: value for key, value in evidence_item.items() if value is not None})
    result["last_tool_names"] = names[-8:]
    result["last_evidence"] = evidence[-8:]
    return result


def context_with_cross_source_snapshot(
    context: dict[str, Any] | None,
    snapshot: Any,  # CrossSourceSnapshot
) -> dict[str, Any]:
    """Persist compact cross-source facts for follow-up question resolution.

    Saves the last 8 facts with their fact_id, label, value, unit,
    data_time, and source_service.  These are used to resolve pronouns
    like "那个顶压" or "刚才那个Si" in follow-up questions.

    Sensor facts are NOT blindly reused across requests — real-time
    sensor queries are re-issued; only short-term MES repeats may be
    served from the 30-second tool cache.
    """

    result = dict(context or empty_tool_context())
    evidence: list[dict[str, Any]] = list(result.get("last_evidence") or [])

    if snapshot is None:
        result["last_evidence"] = evidence[-8:]
        return result

    # Extract cross-source facts
    for fact in getattr(snapshot, "facts", []) or []:
        evidence_item = {
            "fact_id": getattr(fact, "fact_id", None),
            "label": getattr(fact, "label", None),
            "value": getattr(fact, "value", None),
            "unit": getattr(fact, "unit", None),
            "data_time": getattr(fact, "data_time", None),
            "source_service": getattr(fact, "source_service", None),
            "missing": getattr(fact, "missing", False),
        }
        # Only keep non-None fields
        evidence.append({
            key: val for key, val in evidence_item.items() if val is not None
        })

    # Save heat reference for follow-up
    heat_ref = getattr(snapshot, "heat_reference", None)
    if isinstance(heat_ref, dict):
        evidence.append({
            "heat_reference": True,
            "resolved_heat_no": heat_ref.get("resolved_heat_no"),
            "resolution_policy": heat_ref.get("resolution_policy"),
        })

    result["last_evidence"] = evidence[-8:]
    result["last_tool_names"] = result.get("last_tool_names") or []
    return result
