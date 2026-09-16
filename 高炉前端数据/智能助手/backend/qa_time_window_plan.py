"""Deterministic, read-only temporal workflows (QAOPT-R04).

One frozen Asia/Shanghai anchor; existing MCP range queries have inclusive
ends and second-resolution adapters, so windows end one second before the
exclusive boundary. GL02 minute samples cannot appear in both windows.
This module never invokes a model or retries a tool.
"""
from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

VERSION = "qa-time-window-plan-v1"
LOCAL_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
MIN_BASELINE_COVERAGE = 0.8  # evidence-quality policy, not an alarm threshold
_DURATION = r"(半|一|两|二|三|\d+(?:\.\d+)?)\s*(分钟|小时|天)"


def _minutes(number: str, unit: str) -> float:
    value = {"半": .5, "一": 1, "两": 2, "二": 2, "三": 3}.get(number)
    return (value if value is not None else float(number)) * {"分钟": 1, "小时": 60, "天": 1440}[unit]


def _instruction(question: str) -> str:
    return re.sub(r'“[^”]*”|"[^"\n]*"|「[^」]*」', "", question)


def temporal_intent(question: str) -> bool:
    text = _instruction(question)
    recent = re.search(r"(?:最近|近)\s*" + _DURATION, text)
    return bool(recent and ("历史基线" in text or (
        re.search(r"(?:前|此前)\s*" + _DURATION, text)
        and any(word in text for word in ("对比", "相比", "比较", "变化"))
    )))


def build_time_window_plan(question: str, variables: list[str], *, anchor: datetime | None = None) -> dict[str, Any] | None:
    if not temporal_intent(question):
        return None
    question = _instruction(question)
    anchor = anchor or datetime.now(LOCAL_TZ)
    if anchor.tzinfo is None:
        raise ValueError("request anchor must be timezone-aware")
    end = anchor.astimezone(LOCAL_TZ).replace(microsecond=0)
    recent = re.search(r"(?:最近|近)\s*" + _DURATION, question)
    previous = re.search(r"(?:此前|前)\s*" + _DURATION, question)
    kind = "historical_baseline" if "历史基线" in question else "adjacent_windows"
    plan = {"version": VERSION, "kind": kind, "anchor": end.isoformat(), "variables": list(dict.fromkeys(variables)), "steps": [], "windows": []}
    if not recent or not variables or (kind == "adjacent_windows" and not previous):
        plan["blocked_reason"] = "需要明确查询对象及最近时间长度，两个窗口比较还需前一窗口长度。"
        return plan
    recent_minutes = _minutes(*recent.groups())
    previous_minutes = _minutes(*previous.groups()) if previous else 0
    durations = [recent_minutes, previous_minutes] if kind == "adjacent_windows" else [recent_minutes]
    if any(not 1 <= duration * 60 <= 86400 or not float(duration * 60).is_integer() for duration in durations):
        plan["blocked_reason"] = "本时间窗执行器支持每窗大于0且不超过24小时，请缩小窗口。"
        return plan
    start = end - timedelta(minutes=recent_minutes)
    windows = [("recent", "最近窗口", start, end)]
    if kind == "adjacent_windows":
        windows.append(("previous", "前一窗口", start - timedelta(minutes=previous_minutes), start))
    for window_id, label, begin, finish in windows:
        encoded_end = finish - timedelta(seconds=1)
        window = {"id": window_id, "label": label, "start": begin.isoformat(), "end_exclusive": finish.isoformat(), "query_end_inclusive": encoded_end.isoformat()}
        plan["windows"].append(window)
        if kind == "adjacent_windows":
            plan["steps"].append({"id": window_id, "tool": "query_gl02_sensors", "arguments": {"variables": plan["variables"], "query_type": "statistics", "start_time": window["start"], "end_time": window["query_end_inclusive"], "agg": "all"}})
        else:
            for index, variable in enumerate(plan["variables"]):
                plan["steps"].append({"id": f"baseline_{index}", "variable": variable, "tool": "query_gl02_feature_statistics", "arguments": {"variable": variable, "start_time": window["start"], "end_time": window["query_end_inclusive"], "baseline_days": 30}})
    return plan


def _finite(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dt(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=LOCAL_TZ) if result.tzinfo is None else result.astimezone(LOCAL_TZ)
    except (ValueError, TypeError):
        return None


def _stats_valid(stats: dict[str, Any]) -> bool:
    return _finite(stats.get("avg")) and _finite(stats.get("count")) and stats["count"] > 0


def _source(value: Any) -> str:
    if not isinstance(value, dict):
        return "来源未标注"
    return str(value.get("type") or value.get("engine") or value.get("table") or "来源未标注")


def _matched_result(result: dict[str, Any], variable: str, args: dict[str, Any]) -> bool:
    meta = _mapping(result.get("variable"))
    return (result.get("ok") is True and meta.get("variable_name") == variable
            and _dt(result.get("start_time")) == _dt(args["start_time"])
            and _dt(result.get("end_time")) == _dt(args["end_time"])
            and bool(_mapping(result.get("source"))))


def format_time_window_answer(plan: dict[str, Any], results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    lines = ["时间窗统计（不以当前快照代替历史数据）："]
    complete = True
    covered = 0
    required = len(plan["variables"]) * (2 if plan["kind"] == "adjacent_windows" else 1)
    for window in plan["windows"]:
        lines.append(f"{window['label']}：[{window['start']}, {window['end_exclusive']})；结束时刻不计入本窗。")
    for variable in plan["variables"]:
        if plan["kind"] == "adjacent_windows":
            found = []
            for step in plan["steps"]:
                payload = _mapping(results.get(step["id"]))
                rows = payload.get("items")
                items = [item for item in rows if isinstance(item, dict) and item.get("requested_variable") == variable] if isinstance(rows, list) and payload.get("ok") is True else []
                result = _mapping(items[0].get("result")) if len(items) == 1 else {}
                stats = _mapping(result.get("statistics"))
                if not _matched_result(result, variable, step["arguments"]) or not _stats_valid(stats):
                    complete = False
                    lines.append(f"{variable} {step['id']}：未取得有效统计（缺数、查询失败或对象/时间窗不匹配）。")
                    continue
                covered += 1
                unit = str((result.get("variable") or {}).get("unit") or "")
                found.append((stats["avg"], unit))
                lines.append(f"{variable} {step['id']}：均值 {stats['avg']:.6g} {unit}；样本数 {stats['count']}；来源 {_source(result.get('source'))}。")
            if len(found) == 2 and found[0][1] == found[1][1]:
                delta = found[0][0] - found[1][0]
                percent = f"；相对前一窗 {delta / abs(found[1][0]) * 100:.6g}%" if found[1][0] else "；前一窗均值为0，不计算百分比"
                lines.append(f"{variable} 均值差（最近−前一窗）= {delta:.6g} {found[0][1]}{percent}。不同长度窗口比较均值，不比较总量。")
            elif len(found) == 2:
                complete = False
                lines.append(f"{variable} 两窗口单位冲突，不能计算差值。")
        else:
            step = next(item for item in plan["steps"] if item["variable"] == variable)
            result = _mapping(results.get(step["id"]))
            features = _mapping(result.get("features"))
            stats = _mapping(features.get("range"))
            baseline = _mapping(features.get("baseline_30d"))
            if not _matched_result(result, variable, step["arguments"]) or not _stats_valid(stats):
                complete = False
                lines.append(f"{variable}：实时数据库未核实，未取得匹配对象与时间窗的有效统计。")
                continue
            unit = str((result.get("variable") or {}).get("unit") or "")
            lines.append(f"{variable} 最近窗口均值 {stats['avg']:.6g} {unit}；样本数 {stats['count']}；来源 {_source(result.get('source'))}。")
            begin, finish = _dt(baseline.get("baseline_window_start")), _dt(baseline.get("baseline_window_end"))
            coverage, median, iqr, p90 = (baseline.get(key) for key in ("coverage_ratio", "median_ref", "iqr_ref", "p90"))
            baseline_source = _mapping(result.get("baseline_source"))
            candidates = baseline_source.get("variable_candidates")
            candidate_names = candidates if isinstance(candidates, list) else []
            baseline_matches = baseline.get("variable_name") == variable or (
                isinstance(baseline.get("variable_name"), str) and baseline["variable_name"] in candidate_names
            )
            baseline_ok = (begin is not None and finish is not None and begin < finish <= _dt(step["arguments"]["start_time"])
                           and baseline.get("baseline_days") == 30 and _finite(baseline.get("sample_count")) and baseline["sample_count"] > 0
                           and _finite(coverage) and MIN_BASELINE_COVERAGE <= coverage <= 1
                           and _finite(median) and _finite(iqr) and iqr > 0 and _finite(p90)
                           and bool(baseline_source) and baseline_matches)
            if not baseline_ok or result.get("data_limited") is not False:
                complete = False
                lines.append(f"{variable}：历史基线缺失、时间不合格、覆盖低于{MIN_BASELINE_COVERAGE:.0%}或历史采样被截断，无法确认相对历史基线是否偏高。")
                continue
            covered += 1
            z = (stats["avg"] - median) / iqr
            lines.append(f"{variable} 30日基线：[{begin.isoformat()}, {finish.isoformat()})；中位数 {median:.6g} {unit}；IQR {iqr:.6g} {unit}；p90 {p90:.6g} {unit}；覆盖率 {coverage:.1%}；样本数 {baseline['sample_count']}；来源 {_source(result.get('baseline_source'))}。")
            lines.append(f"相对基线中位数{'偏高' if stats['avg'] > median else '未偏高'}；{'高于' if stats['avg'] > p90 else '未高于'}历史p90。标准化偏离=(窗口均值−基线中位数)/IQR={z:.6g}；这是历史分布比较，不能据此认定生产异常或因果。")
    if not complete:
        lines.append("证据不完整：保留以上有效数据，不对缺失窗口或基线补写结论。")
    return {"answer": "\n".join(lines), "complete": complete, "covered": covered, "required": required}


async def execute_time_window_plan(plan: dict[str, Any], *, available_tools: set[str], validate: Any, call: Any, on_start: Any, on_result: Any, max_calls: int) -> dict[str, Any]:
    """Run same-server steps serially, with no retry after any failure.

    callbacks persist/emit evidence at each step; lifecycle errors propagate
    rather than trigger a second request. Cancellation always propagates.
    """
    if plan.get("blocked_reason") or len(plan["steps"]) > max_calls:
        return {"ok": True, "tool_used": False, "answer": plan.get("blocked_reason") or "查询步骤超过本轮预算，请减少对象。", "complete": False, "tool_trace": [], "model_request_count": 0, "grounding_status": "no_verified_evidence"}
    results, trace = {}, []
    executed = 0
    for step in plan["steps"]:
        name, args = step["tool"], step["arguments"]
        policy = validate(name, args) if name in available_tools else {"ok": False, "errors": ["tool_unavailable"]}
        item = {"round": 0, "route": "deterministic_time_windows", "step_id": step["id"], "tool": name, "arguments": args, "policy": policy}
        if not policy["ok"]:
            payload = {"ok": False, "error": "tool_policy_or_availability"}
        else:
            on_start(item)
            executed += 1
            try:
                payload = await call(name, args)
                if not isinstance(payload, dict):
                    payload = {"ok": False, "error": "invalid_tool_output"}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                payload = {"ok": False, "error": type(exc).__name__}
        results[step["id"]] = payload
        item["result"] = {"ok": payload.get("ok"), "error": payload.get("error")}
        trace.append(item)
        on_result(item, payload)
    summary = format_time_window_answer(plan, results)
    return {"ok": True, "tool_used": executed > 0, **summary, "tool_trace": trace, "answer_route": "deterministic_time_windows", "model_request_count": 0, "grounding_status": "verified_complete" if summary["complete"] else "partial_or_missing_evidence", "time_window_plan": plan}
