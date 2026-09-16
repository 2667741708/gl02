"""Readable, bounded tool facts after model failure; never dump raw JSON (QAOPT-E01/O02)."""
import json
import math
import re
from collections.abc import Mapping

VERSION = "qa-tool-fallback-v1"
LABELS = {"variable_name":"测点", "requested_variable":"请求对象", "value":"值", "unit":"单位",
          "ts":"数据时间", "source_time":"来源时间", "start_time":"起始时间", "end_time":"结束时间",
          "count":"样本数", "avg":"均值", "min":"最小值", "max":"最大值", "stddev":"标准差",
          "mean":"均值", "first":"首值", "last":"末值", "delta":"变化量", "main_label":"诊断标签",
          "si_avg":"Si均值", "heat_no":"炉次", "workdate":"生产日期", "profile":"数据来源",
          "engine":"来源引擎", "read_policy":"访问策略", "version":"版本"}
CONTAINERS = {"result", "items", "rows", "data", "latest", "variable", "statistics", "source",
              "snapshot", "diagnosis", "points", "values", "results", "statistics_by_variable"}
METRIC = re.compile(r"^(?:P_|T_|DP_|F_|Gas|Si|PCI|O2|CO2?|H2|Heat|Coke|Wind)[A-Za-z0-9_]*$")


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
