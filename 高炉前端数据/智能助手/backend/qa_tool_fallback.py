"""Readable, bounded tool facts after model failure; never dump raw JSON (QAOPT-E01/O02)."""
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION = "qa-tool-fallback-v2"
LABELS = {"variable_name":"测点", "requested_variable":"请求对象", "value":"值", "unit":"单位",
          "ts":"数据时间", "source_time":"来源时间", "start_time":"起始时间", "end_time":"结束时间",
          "count":"样本数", "avg":"均值", "min":"最小值", "max":"最大值", "stddev":"标准差",
          "mean":"均值", "first":"首值", "last":"末值", "delta":"变化量", "main_label":"诊断标签",
          "si_avg":"Si均值", "heat_no":"炉次", "workdate":"生产日期", "profile":"数据来源",
          "engine":"来源引擎", "read_policy":"访问策略", "version":"版本"}
CONTAINERS = {"result", "items", "rows", "data", "latest", "variable", "statistics", "source",
              "snapshot", "diagnosis", "points", "values", "results", "statistics_by_variable"}
METRIC = re.compile(r"^(?:P_|T_|DP_|F_|Gas|Si|PCI|O2|CO2?|H2|Heat|Coke|Wind)[A-Za-z0-9_]*$")
CHART_URL = re.compile(r"/data/mcp_charts/[A-Za-z0-9_-]+\.png\Z")


def chart_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    except (ValueError, TypeError):
        return None


def trend_chart_answer(payload, arguments=None, labels=None):
    """REQ-QA-CHART-COVERAGE-20260917: preserve typed chart evidence and gaps."""
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        return "趋势图未完成，本轮没有可核验的图表结果。"
    arguments, labels = arguments or {}, labels or {}
    requested = arguments.get("variables") or payload.get("requested_variables") or payload.get("variables")
    if not isinstance(requested, list) or not requested or len(requested) > 24:
        return "趋势图请求对象未核实，不能确认覆盖范围。"
    names = list(dict.fromkeys(str(name) for name in requested))
    if any(not METRIC.fullmatch(name) for name in names):
        return "趋势图请求对象未核实，不能确认覆盖范围。"
    start, end = chart_time(payload.get("start_time")), chart_time(payload.get("end_time"))
    if not start or not end or start >= end:
        return "趋势图时间窗未核实，不能作为本次问题的证据。"
    for key, actual in (("start_time", start), ("end_time", end)):
        if key in arguments and chart_time(arguments[key]) != actual:
            return "趋势图返回时间窗与请求不一致，不能作为本次问题的证据。"
    url = str(payload.get("image_url") or "")
    safe_image = bool(CHART_URL.fullmatch(url))
    valid, rows, rejected = {}, [], set()
    series = payload.get("series")
    if not isinstance(series, list) or len(series) > 24:
        series = []
    for item in series:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("requested_variable") or "")
        if name not in names:
            continue
        if name in valid:
            rejected.add(name)
            continue
        meta, summary, source = item.get("variable"), item.get("summary"), item.get("source")
        if not all(isinstance(x, Mapping) for x in (meta, summary, source)):
            continue
        last = summary.get("last")
        if not isinstance(last, Mapping) or source.get("read_policy") != "readonly":
            continue
        if meta.get("variable_name") not in (None, name):
            continue
        count, value, timestamp = summary.get("count"), last.get("value"), chart_time(last.get("ts"))
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        if not timestamp or not start <= timestamp <= end:
            continue
        valid[name] = (meta, summary, source, last, timestamp)
    for name in rejected:
        valid.pop(name, None)
    covered = [name for name in names if name in valid]
    missing = [name for name in names if name not in valid]
    title = "已生成趋势图" if safe_image and covered else "趋势图未完整交付"
    lines = [title + f"；请求 {len(names)} 个测点，可核验 {len(covered)} 个。",
             f"时间范围：{start.isoformat()} 至 {end.isoformat()}。"]
    for name in covered:
        meta, summary, source, last, timestamp = valid[name]
        unit = scalar(meta.get("unit")) or "（单位未核实）"
        label = scalar(labels.get(name)) or name
        profile = scalar(source.get("profile") or source.get("engine")) or "来源未标明"
        quality = scalar(last.get("quality")) or "未标明"
        lines.append(f"- {label}：有效样本 {summary['count']}，末值 {last['value']}{unit}；"
                     f"数据时间 {timestamp.isoformat()}；质量 {quality}；来源 {profile} / readonly。")
    if missing:
        lines.append("未完成测点：" + "、".join(missing) + "。不能视为全部测点已回答。")
    if safe_image and covered:
        lines.append(f"![GL02趋势图]({url})")
    else:
        lines.append("图片地址未核实或没有可核验序列，不能确认图表已交付。")
    limit = payload.get("max_points_per_variable")
    if isinstance(limit, int) and any(valid[name][1]["count"] >= limit for name in covered):
        lines.append("部分测点达到返回点数上限，完整时间覆盖尚未核实。")
    lines.append("有效样本数不等于完整时间覆盖；未插值、未推断当前炉况。")
    return "\n".join(lines)


def model_result_text(name, result_text, arguments, limit):
    """Keep the evidence ledger intact; bound only the separate model projection."""
    if len(result_text) <= limit:
        return result_text
    try:
        payload = json.loads(result_text)
    except (ValueError, TypeError):
        return json.dumps({"ok": False, "error": "INVALID_TOOL_JSON"})
    if isinstance(payload, Mapping) and isinstance(payload.get("result"), Mapping):
        payload = payload["result"]
    if name == "plot_gl02_trends":
        excerpt = trend_chart_answer(payload, arguments)
    else:
        lines, _ = facts(payload)
        excerpt = "\n".join(lines)
    return json.dumps({"ok": isinstance(payload, Mapping) and payload.get("ok") is not False,
                       "bounded_projection": True, "complete_evidence_retained": True,
                       "excerpt": excerpt[:max(0, limit - 250)],
                       "warning": "只展示事实摘录，不能据此确认全部子任务完成。"}, ensure_ascii=False)


def scalar(value):
    if isinstance(value, bool) or value is None: return None
    if isinstance(value, (float, int)):
        return str(value) if math.isfinite(value) else None
    if not isinstance(value, str) or len(value) > 160: return None
    # Tool fields are untrusted. Exclude connection strings, executable syntax,
    # and secrets even if carried in a normally public name/unit field.
    if re.search(r"https?://|://|password|passwd|secret|token|cookie|authorization|[\r\n{}<>`]|SELECT\s|INSERT\s|\$\w+\s*=", value, re.I): return None
    return value


def facts(payload):
    lines, omitted = [], False
    def walk(value, path="", depth=0):
        nonlocal omitted
        if depth > 7 or len(lines) >= 80:
            omitted = True
            return
        if isinstance(value, Mapping):
            for key, child in value.items():
                key = str(key)
                if key in LABELS or METRIC.fullmatch(key):
                    label = (path + " / " if path else "") + LABELS.get(key, key)
                    if isinstance(child, (Mapping, list)):
                        walk(child, label, depth+1)
                    elif (text := scalar(child)) is not None:
                        lines.append(label + "：" + text)
                elif key in CONTAINERS:
                    walk(child, path, depth+1)
        elif isinstance(value, list):
            if len(value) > 20: omitted = True
            for index, item in enumerate(value[:20], 1):
                walk(item, (path + " / " if path else "") + "记录" + str(index), depth+1)
    walk(payload)
    return lines, omitted


def summarize(results):
    blocks, missing = [], []
    for item in results:
        name = scalar(str(item.get("name") or item.get("tool") or "只读工具")) or "只读工具"
        try: payload = json.loads(str(item.get("result_text") or ""))
        except (ValueError, TypeError): payload = None
        if isinstance(payload, Mapping) and isinstance(payload.get("result"), Mapping): payload = payload["result"]
        if not isinstance(payload, Mapping) or payload.get("ok") is False or payload.get("error"):
            missing.append(name + "：未完成或未取得可核验事实。")
            continue
        if name == "plot_gl02_trends":
            blocks.append("【趋势图】\n" + trend_chart_answer(payload, item.get("arguments")))
            continue
        lines, omitted = facts(payload)
        if lines:
            blocks.append("【" + name + "】\n" + "\n".join(lines))
            if omitted: blocks.append("本工具只展示有界事实摘录，未展示部分不得视为已完整回答。")
        else:
            missing.append(name + "：仅有未支持的结构或路由元数据，未计作问题事实。")
    parts = ["以下是本轮已取得的只读事实；后续分析未完成，不能据此确认全部子任务已回答。"] if blocks else ["实时数据库未核实：本轮没有可展示的问题事实。"]
    parts.extend(blocks)
    if missing: parts.append("未完成部分：\n" + "\n".join(missing))
    return "\n\n".join(parts)
