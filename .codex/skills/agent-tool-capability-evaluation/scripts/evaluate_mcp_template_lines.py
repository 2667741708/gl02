"""Parse and evaluate every executable line in the PT MCP prompt template.

Safety contract: listing is the default; live SSE calls require --execute.  Each
unique prompt is sent at most once, sequentially, and failures are never retried.
JSONL checkpoints are flushed after every row so a long audit can resume.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


SCHEMA = "bf.agent-tool-capability.mcp-template-lines.v1"
EVALUATION_ID = "Q-MCP-TEMPLATE-LINE-EVALUATION-20260813"
QUESTION_HINTS = (
    "查", "看", "告诉", "说", "画", "列", "读", "当前", "现在", "最近", "有没有",
    "是否", "是不是", "多少", "怎么样", "如何", "对比", "比较", "分析", "给我", "帮我", "这炉",
    "检索", "涨", "降",
)
PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}")
BARE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\s*[/,，]\s*[A-Za-z][A-Za-z0-9_]*)*$")
NON_QUESTION_EXAMPLE_PREFIXES = (
    "无数据：", "多样品：", "缺失值：", "查询失败：", "超时：", "权限不足：",
    "助手：", "assistant:",
)
CATALOG_QUERY_TERMS = ("对应哪个点位", "标准变量", "变量清单", "映射", "能查哪些点", "可用的点")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def normalize_prompt(text: str) -> str:
    return re.sub(r"\s+", "", text).strip("。！？?!：:").casefold()


def load_catalog(path: Path) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    objects = payload.get("objects") or []
    aliases: dict[str, set[str]] = {}
    for obj in objects:
        object_id = str(obj.get("object_id") or "")
        terms = [object_id, obj.get("display_name"), *(obj.get("semantic_aliases") or [])]
        for term in terms:
            key = normalize_prompt(str(term or ""))
            if key:
                aliases.setdefault(key, set()).add(object_id)
    return objects, aliases


def resolve_expected_objects(text: str, aliases: dict[str, set[str]]) -> list[str]:
    normalized = normalize_prompt(text)
    matches: list[tuple[int, int, str]] = []
    for alias, object_ids in aliases.items():
        if len(alias) < 2:
            continue
        start = normalized.find(alias)
        if start < 0 or len(object_ids) != 1:
            continue
        matches.append((start, start + len(alias), next(iter(object_ids))))
    matches.sort(key=lambda item: (-(item[1] - item[0]), item[0], item[2]))
    occupied: list[tuple[int, int]] = []
    selected: list[tuple[int, str]] = []
    for start, end, object_id in matches:
        if any(start < used_end and end > used_start for used_start, used_end in occupied):
            continue
        occupied.append((start, end))
        selected.append((start, object_id))
    selected.sort()
    result: list[str] = []
    for _, object_id in selected:
        if object_id not in result:
            result.append(object_id)
    range_requested = any(token in normalized for token in ("a-d", "a到d", "a、b、c、d", "abcd", "四个点"))
    if range_requested and any(token in normalized for token in ("顶温", "炉顶温度", "上升管煤气温度")):
        result = [item for item in result if item != "T_top"]
        result.extend(item for item in ("T_top_A", "T_top_B", "T_top_C", "T_top_D") if item not in result)
    if range_requested and any(token in normalized for token in ("顶压", "炉顶压力", "上升管煤气压力")):
        result = [item for item in result if item != "P_top"]
        result.extend(item for item in ("P_top_A", "P_top_B", "P_top_C", "P_top_D") if item not in result)
    for layer, sector in re.findall(r"(7|8|9|1[0-6])层([A-H])", text, flags=re.I):
        object_id = f"T_body_L{layer}_{sector.upper()}"
        if object_id not in result:
            result.append(object_id)
    generic_aliases = (
        (("炉顶的温度", "炉顶温度", "综合顶温"), "T_top"),
        (("炉顶的压力", "炉顶压力", "综合顶压"), "P_top"),
        (("风压",), "P_blast"),
        (("风温",), "T_blast"),
        (("风量", "送风量"), "Q_blast"),
    )
    for terms, object_id in generic_aliases:
        if any(term in text for term in terms) and object_id not in result:
            result.append(object_id)
    return result


def classify_capabilities(text: str) -> list[str]:
    lowered = text.casefold()
    result: list[str] = []
    rules = (
        ("catalog", ("对应哪个点位", "标准变量", "变量清单", "点位", "映射", "能查哪些点", "可用的点")),
        ("report", ("日报", "周报", "月报", "报表")),
        ("history_search", ("历史问答", "以前是否问过", "之前有没有问过")),
        ("diagnosis_snapshot", ("炉况", "诊断依据", "数据质量", "主要异常")),
        ("correlation", ("相关", "关系图", "相关矩阵", "散点")),
        ("plot", ("画", "曲线", "走势图", "趋势图", "直方图", "箱线图", "热力")),
        ("statistics", ("平均", "均值", "标准差", "波动", "稳不稳", "最高", "最低", "最大值", "最小值", "变化大", "cv", "极差")),
        ("history", ("最近", "过去", "昨晚", "趋势", "走势", "升了", "降了", "变化", "半小时", "一小时", "两小时", "八小时")),
        ("latest", ("现在", "当前", "最新", "是多少", "多少")),
        ("heat_chemistry", ("铁水", "炉次", "炉号", "铁次", "渣", "烧结", "化验", "成分", "出了多少铁")),
        ("calculation", ("计算", "公式", "比值", "标准差", "均值", "平均", "相关系数", "cv", "极差")),
        ("sensor_grounded_inference", ("推测", "判断", "是否足以", "异常", "稳不稳", "状态")),
    )
    for capability, terms in rules:
        if any(term in lowered for term in terms):
            result.append(capability)
    return result or ["unknown"]


def expected_tool_families(capabilities: list[str]) -> list[str]:
    result: list[str] = []
    mapping = {
        "catalog": "find_gl02_variables|search_business_objects|list_gl02_variables|get_gl02_variable_metadata",
        "report": "list_recent_reports|read_report_excerpt|query_bf2_operation_log_report",
        "history_search": "search_qa_messages",
        "diagnosis_snapshot": "get_latest_furnace_snapshot|query_gl02_feature_statistics|query_gl02_statistics|plot_gl02_analysis",
        "correlation": "plot_gl02_analysis",
        "plot": "plot_gl02_*",
        "statistics": "query_gl02_sensors|query_gl02_statistics|query_gl02_feature_statistics",
        "history": "query_gl02_sensors|query_gl02_history|plot_gl02_*",
        "latest": "query_gl02_sensors|get_latest_gl02_value",
        "heat_chemistry": "imes__*",
    }
    for capability in capabilities:
        family = mapping.get(capability)
        if family and family not in result:
            result.append(family)
    return result


def row_disposition(text: str) -> tuple[str, str | None]:
    stripped = text.strip()
    if not stripped:
        return "skipped", "blank"
    if stripped.startswith(NON_QUESTION_EXAMPLE_PREFIXES):
        return "skipped", "assistant_example"
    if stripped.startswith(("用户：", "user:")):
        stripped = stripped.split("：", 1)[-1].split(":", 1)[-1].strip()
    if PLACEHOLDER_RE.search(stripped):
        return "skipped", "unresolved_placeholder"
    if BARE_ID_RE.fullmatch(stripped):
        return "skipped", "bare_identifier_example"
    if not any(hint in stripped for hint in QUESTION_HINTS):
        return "skipped", "not_an_executable_prompt"
    return "ready", None


def parse_template(template: Path, catalog: Path) -> list[dict[str, Any]]:
    text = template.read_text(encoding="utf-8")
    _, aliases = load_catalog(catalog)
    rows: list[dict[str, Any]] = []
    headings: list[str] = []
    in_fence = False
    fence_language = ""
    previous_line = ""
    seen: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", raw)
        if heading and not in_fence:
            level = len(heading.group(1))
            headings = headings[: level - 1] + [heading.group(2)]
            previous_line = raw
            continue
        fence = re.match(r"^```\s*([^`]*)$", raw.strip())
        if fence:
            if in_fence:
                in_fence = False
                fence_language = ""
            else:
                in_fence = True
                fence_language = fence.group(1).strip().casefold()
            previous_line = raw
            continue
        if not in_fence or fence_language not in {"", "text"}:
            previous_line = raw
            continue
        prompt = raw.strip()
        status, reason = row_disposition(prompt)
        if prompt.startswith(("用户：", "user:")):
            prompt = re.sub(r"^(?:用户|user)\s*[：:]\s*", "", prompt, flags=re.I).strip()
        normalized = normalize_prompt(prompt)
        case_id = f"L{lineno:04d}-{sha256_text(prompt)[:8]}"
        duplicate_of = None
        if status == "ready" and normalized in seen:
            status = "duplicate"
            duplicate_of = seen[normalized]
        elif status == "ready":
            seen[normalized] = case_id
        capabilities = classify_capabilities(prompt) if prompt else []
        rows.append(
            {
                "case_id": case_id,
                "source_line": lineno,
                "section": " > ".join(headings),
                "prompt": prompt,
                "source_status": status,
                "skip_reason": reason,
                "duplicate_of": duplicate_of,
                "expected": {
                    "objects": resolve_expected_objects(prompt, aliases),
                    "capabilities": capabilities,
                    "tool_families": expected_tool_families(capabilities),
                },
            }
        )
        previous_line = raw
    return rows


def actual_tools(raw: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in raw.get("tool_starts") or []:
        if not isinstance(event, dict):
            continue
        items.append(
            {
                "server_id": event.get("server_id"),
                "tool": event.get("tool"),
                "arguments": event.get("arguments") or {},
                "round": event.get("round"),
                "step_id": event.get("step_id"),
            }
        )
    if not items:
        for event in raw.get("tool_results") or []:
            if not isinstance(event, dict):
                continue
            tool = event.get("tool") or ((event.get("summary") or {}).get("tool") if isinstance(event.get("summary"), dict) else None)
            if not tool:
                continue
            items.append(
                {
                    "server_id": event.get("server_id"),
                    "tool": tool,
                    "arguments": event.get("arguments") or {},
                    "round": event.get("round"),
                    "step_id": event.get("step_id"),
                    "result_only": True,
                }
            )
    evidence_rows = [
        item for item in [*(raw.get("tool_results") or []), *(raw.get("source_status") or [])]
        if isinstance(item, dict)
    ]
    used: set[int] = set()
    for item in items:
        for index, evidence in enumerate(evidence_rows):
            if index in used or evidence.get("tool") != item.get("tool"):
                continue
            item["server_id"] = item.get("server_id") or evidence.get("server_id")
            item["step_id"] = item.get("step_id") or evidence.get("step_id")
            item["elapsed_ms"] = evidence.get("elapsed_ms")
            item["cache_hit"] = evidence.get("cache_hit")
            used.add(index)
            break
    return items


def tools_are_cross_mcp(tools: list[dict[str, Any]], raw: dict[str, Any]) -> bool:
    if raw.get("cross_service"):
        return True
    servers = {str(item.get("server_id") or "") for item in tools if item.get("server_id")}
    return len(servers) >= 2


def actual_objects(tools: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for item in tools:
        args = item.get("arguments") or {}
        values: list[Any] = []
        for key in ("variable", "variables"):
            value = args.get(key)
            values.extend(value if isinstance(value, list) else [value] if value else [])
        for value in values:
            text = str(value)
            if text and text not in result:
                result.append(text)
    return result


def family_matches(expected: str, actual: str) -> bool:
    for candidate in expected.split("|"):
        if candidate.endswith("*") and actual.startswith(candidate[:-1]):
            return True
        if actual == candidate:
            return True
    return False


def recompare_checkpoint_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raw")
    if row.get("request_count") == 1 and isinstance(raw, dict):
        result = compare_row(row, raw)
        row.update(result)
        row["status"] = "passed" if result["comparison"]["overall_passed"] else "failed"
    return row


def refresh_checkpoint_metadata(row: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    if not current:
        return row
    refreshed = dict(row)
    for key in ("source_line", "section", "prompt", "source_status", "skip_reason", "duplicate_of", "expected"):
        refreshed[key] = current.get(key)
    return refreshed


def evidence_tokens(raw: dict[str, Any]) -> dict[str, bool]:
    answer = str(raw.get("answer") or "")
    result_text = json.dumps(raw.get("tool_results") or [], ensure_ascii=False, default=str)
    return {
        "answer_nonempty": bool(answer.strip()),
        "has_value": bool(re.search(r"(?<!\w)-?\d+(?:\.\d+)?", answer)),
        "has_time": bool(re.search(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}:\d{2}", answer)) or "数据时间" in answer,
        "has_source": any(token in answer for token in ("来源", "gl02", "imes", "PostgreSQL", "pSpace")),
        "has_formula": any(token in answer for token in ("公式", "÷", "×", "Pearson", "CV", "标准差")),
        "tool_has_time": bool(re.search(r"20\d{2}-\d{2}-\d{2}T", result_text)),
        "tool_has_value": bool(re.search(r'"(?:value|avg|si_avg|pearson_r)"\s*:\s*-?\d', result_text)),
    }


def full_tool_payload(raw: dict[str, Any], tool: str) -> dict[str, Any]:
    for item in raw.get("tool_results") or []:
        if item.get("tool") == tool and isinstance(item.get("result"), dict):
            payload = item["result"]
            if payload.get("derived") or payload.get("items"):
                return payload
    for item in raw.get("source_status") or []:
        if item.get("tool") != tool:
            continue
        try:
            payload = json.loads(str(item.get("result_text") or ""))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def answer_mentions_number(answer: str, value: Any, tolerance: float = 1e-6) -> bool:
    try:
        expected = float(value)
    except (TypeError, ValueError):
        return False
    for token in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?", answer):
        actual = float(token)
        if abs(actual - expected) <= max(tolerance, abs(expected) * 0.005):
            return True
    return False


def requested_answer_checks(row: dict[str, Any], raw: dict[str, Any]) -> dict[str, bool]:
    prompt = str(row.get("prompt") or "")
    answer = str(raw.get("answer") or "")
    lowered = answer.casefold()
    checks: dict[str, bool] = {}
    field_terms = (
        ("样本数", ("样本", "count")),
        ("标准差", ("标准差", "stddev")),
        ("极差", ("极差",)),
        ("首末值", ("首值", "末值", "起始值", "结束值")),
        ("变化量", ("变化量", "delta")),
        ("斜率", ("斜率", "slope")),
        ("变异系数", ("变异系数", "cv")),
    )
    prompt_lowered = prompt.casefold()
    for requested, answer_terms in field_terms:
        if requested.casefold() in prompt_lowered or (requested == "变异系数" and "cv" in prompt_lowered):
            checks[f"requested_{requested}"] = any(term.casefold() in lowered for term in answer_terms)
    if "公式" in prompt or "不要省略公式" in prompt:
        checks["requested_formula"] = any(term in answer for term in ("公式", "÷", "×", "=", "/"))
    if any(term in prompt for term in ("推测", "判断", "是否足以", "稳不稳")):
        checks["requested_reasoning_or_boundary"] = any(
            term in answer for term in ("推测", "判断", "足以", "不足", "证据", "只能", "稳定", "波动")
        )
    if "Pearson" in prompt or "相关系数" in prompt:
        payload = full_tool_payload(raw, "plot_gl02_analysis")
        correlation = (payload.get("derived") or {}).get("correlation") or {}
        pearson_r = correlation.get("pearson_r")
        checks["requested_pearson_r"] = (
            pearson_r is not None
            and answer_mentions_number(answer, pearson_r)
            and not any(term in answer for term in ("未包含具体的 Pearson", "没有返回相关系数", "未返回相关系数"))
        )
        if "对齐样本" in prompt:
            aligned_count = correlation.get("aligned_count")
            checks["requested_aligned_count"] = (
                aligned_count is not None
                and answer_mentions_number(answer, aligned_count, tolerance=0.0)
                and not any(term in answer for term in ("未包含", "没有返回", "未返回"))
            )
    return checks


def declared_units(raw: dict[str, Any]) -> list[str]:
    units: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            unit = value.get("unit")
            if isinstance(unit, str) and unit.strip() and unit.strip() not in units:
                units.append(unit.strip())
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(raw.get("tool_results") or [])
    visit(raw.get("source_status") or [])
    return units


def core_evaluations(row: dict[str, Any], comparison: dict[str, Any], tools: list[dict[str, Any]], raw: dict[str, Any]) -> dict[str, Any]:
    capabilities = set((row.get("expected") or {}).get("capabilities") or [])
    objects = (row.get("expected") or {}).get("objects") or []
    answer_passed = bool(comparison.get("final_answer_evidence_fidelity_passed"))
    tool_passed = bool(comparison.get("tool_contract_passed"))

    sensor_applicable = bool(objects) and bool(
        capabilities & {"latest", "history", "statistics", "plot", "correlation", "sensor_grounded_inference"}
    )
    calculation_applicable = bool(capabilities & {"calculation", "statistics", "correlation"})
    multi_tool = len(tools) >= 2
    cross_mcp = tools_are_cross_mcp(tools, raw)
    multi_applicable = multi_tool or cross_mcp
    return {
        "sensor_grounded_inference": {
            "status": "passed" if sensor_applicable and tool_passed and answer_passed else "failed" if sensor_applicable else "not_applicable"
        },
        "deterministic_tool_augmented_computation": {
            "status": "passed" if calculation_applicable and tool_passed and answer_passed else "failed" if calculation_applicable else "not_applicable"
        },
        "multi_tool_cross_mcp_orchestration": {
            "status": "passed" if multi_applicable and tool_passed else "failed" if multi_applicable else "not_applicable",
            "actual_tool_count": len(tools),
            "cross_mcp": cross_mcp,
        },
        "final_answer_evidence_fidelity": {"status": "passed" if answer_passed else "failed"},
    }


def compare_row(row: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    tools = actual_tools(raw)
    tool_names = [str(item.get("tool") or "") for item in tools]
    actual_ids = actual_objects(tools)
    expected = row["expected"]
    expected_ids = expected.get("objects") or []
    expected_families = expected.get("tool_families") or []
    tool_family_match = (
        True if not expected_families else any(family_matches(family, tool) for family in expected_families for tool in tool_names)
    )
    object_match = True if not expected_ids else set(expected_ids).issubset(set(actual_ids))
    evidence = evidence_tokens(raw)
    capabilities = set(expected.get("capabilities") or [])
    required_answer = {
        "answer_nonempty": True,
        "has_time": bool(capabilities & {"latest", "history", "statistics", "plot", "correlation", "sensor_grounded_inference"}),
        "has_source": bool(capabilities & {"latest", "history", "statistics", "plot", "correlation", "heat_chemistry", "diagnosis_snapshot", "report", "history_search", "sensor_grounded_inference"}),
        "has_formula": bool(capabilities & {"calculation"}),
    }
    answer_checks = {key: (not required or evidence[key]) for key, required in required_answer.items()}
    units = declared_units(raw)
    if units:
        answer_checks["declared_units_present"] = all(unit in str(raw.get("answer") or "") for unit in units)
    answer_checks.update(requested_answer_checks(row, raw))
    tool_contract = bool(raw.get("ok")) and "final" in (raw.get("events") or []) and bool(tools) and tool_family_match and object_match
    answer_contract = all(answer_checks.values())
    issue_class = "passed"
    if not bool(raw.get("ok")) or "error" in (raw.get("events") or []):
        issue_class = "runtime_error"
    elif not tools and expected_families:
        issue_class = "advertised_not_supported"
    elif not tool_family_match and tools and any(term in str(row.get("prompt") or "") for term in CATALOG_QUERY_TERMS):
        issue_class = "oracle_invalid"
    elif not tool_family_match or not object_match:
        issue_class = "implementation_defect"
    elif not answer_contract:
        issue_class = "answer_contract_failed"
    core = core_evaluations(
        row,
        {
            "tool_contract_passed": tool_contract,
            "final_answer_evidence_fidelity_passed": answer_contract,
        },
        tools,
        raw,
    )
    return {
        "actual": {
            "tools": tools,
            "objects": actual_ids,
            "events": raw.get("events") or [],
            "answer": raw.get("answer") or "",
            "elapsed_ms": raw.get("elapsed_ms"),
            "evidence": evidence,
        },
        "comparison": {
            "tool_family_match": tool_family_match,
            "object_match": object_match,
            "answer_checks": answer_checks,
            "tool_contract_passed": tool_contract,
            "final_answer_evidence_fidelity_passed": answer_contract,
            "overall_passed": tool_contract and answer_contract,
            "issue_class": issue_class,
            "core_evaluations": core,
        },
    }


def load_checkpoint(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append_checkpoint(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        handle.flush()


def rewrite_checkpoint(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    temporary.replace(path)


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or row.get("source_status") or "unknown") for row in rows)
    executed = [row for row in rows if row.get("status") in {"passed", "failed", "error"}]
    failure_reasons: Counter[str] = Counter()
    section_summary: dict[str, Counter[str]] = {}
    core_summary: dict[str, Counter[str]] = {}
    for row in executed:
        section_summary.setdefault(str(row.get("section") or ""), Counter())[str(row.get("status") or "unknown")] += 1
        comparison = row.get("comparison") or {}
        if not comparison:
            failure_reasons["execution_error"] += 1
            failure_reasons["class_runtime_error"] += 1
            continue
        if comparison.get("issue_class") != "passed":
            failure_reasons[f"class_{comparison.get('issue_class', 'unknown')}"] += 1
        if not comparison.get("tool_contract_passed"):
            failure_reasons["tool_contract"] += 1
        if not comparison.get("tool_family_match", True):
            failure_reasons["tool_family_mismatch"] += 1
        if not comparison.get("object_match", True):
            failure_reasons["object_mismatch"] += 1
        for name, passed in (comparison.get("answer_checks") or {}).items():
            if not passed:
                failure_reasons[f"answer_{name}"] += 1
        for name, result in (comparison.get("core_evaluations") or {}).items():
            core_summary.setdefault(name, Counter())[str((result or {}).get("status") or "not_tested")] += 1
    return {
        "total_template_lines": len(rows),
        "status_counts": dict(sorted(statuses.items())),
        "executed": len(executed),
        "tool_contract_passed": sum(bool((row.get("comparison") or {}).get("tool_contract_passed")) for row in executed),
        "answer_fidelity_passed": sum(bool((row.get("comparison") or {}).get("final_answer_evidence_fidelity_passed")) for row in executed),
        "overall_passed": sum(bool((row.get("comparison") or {}).get("overall_passed")) for row in executed),
        "request_count": sum(int(row.get("request_count") or 0) for row in rows),
        "failure_reasons": dict(failure_reasons.most_common()),
        "sections": {name: dict(counts) for name, counts in section_summary.items()},
        "core_evaluations": {name: dict(counts) for name, counts in core_summary.items()},
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# MCP 模板逐行调用对比报告",
        "",
        f"> 评估编号：`{report['evaluation_id']}`  ",
        f"> 生成时间：{report['created_at']}  ",
        f"> 实际请求数：{report['summary']['request_count']}（失败不自动重发）",
        "",
        "| 用例 | 源行 | 模板 | 预期对象/能力 | 实际工具 | 工具合同 | 答案忠实度 | 状态 |",
        "| --- | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        comparison = row.get("comparison") or {}
        actual = row.get("actual") or {}
        prompt = str(row.get("prompt") or "").replace("|", "\\|")[:90]
        expected = row.get("expected") or {}
        expected_text = ", ".join((expected.get("objects") or []) + (expected.get("capabilities") or []))
        tools = ", ".join(str(item.get("tool") or "") for item in actual.get("tools") or [])
        tool_state = "✓" if comparison.get("tool_contract_passed") else "✗" if comparison else "—"
        answer_state = "✓" if comparison.get("final_answer_evidence_fidelity_passed") else "✗" if comparison else "—"
        lines.append(
            f"| `{row['case_id']}` | {row['source_line']} | {prompt} | {expected_text[:80]} | {tools or '—'} | {tool_state} | {answer_state} | {row.get('status') or row.get('source_status')} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def import_runner(repo_root: Path) -> Callable[[str, str, int], dict[str, Any]]:
    tools_dir = repo_root / "tools"
    sys.path.insert(0, str(tools_dir))
    from probe_8093_cross_mcp_computation import run_once  # type: ignore

    return run_once


def discover_repo_root(script: Path) -> Path:
    candidates = [Path.cwd().resolve(), script.parents[4]]
    for candidate in candidates:
        if (candidate / "PT" / "MCP可执行功能及口语调用模板.md").exists() and (candidate / "tools").is_dir():
            return candidate
    raise RuntimeError("无法定位项目根目录；请在包含 PT/ 和 tools/ 的项目目录中运行。")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    script = Path(__file__).resolve()
    repo_root = discover_repo_root(script)
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=repo_root / "PT" / "MCP可执行功能及口语调用模板.md")
    parser.add_argument("--catalog", type=Path, default=repo_root / "数据库同步和存取" / "config" / "点位语义目录.json")
    parser.add_argument("--url", default="http://10.30.220.12:8093/api/qa/chat")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reclassify-report", type=Path, help="re-score an existing report without any live request")
    parser.add_argument("--start", type=int, default=1, help="1-based ready/duplicate sequence index")
    parser.add_argument("--case-id", action="append", default=[], help="execute only the selected stable case id; repeatable")
    parser.add_argument("--limit", type=int, default=0, help="maximum unique live requests; 0 means all selected")
    parser.add_argument("--section", default="", help="case-insensitive substring filter on heading path")
    parser.add_argument("--checkpoint", type=Path, default=repo_root / "logs" / "mcp_template_line_eval" / "checkpoint.jsonl")
    parser.add_argument("--output", type=Path, default=repo_root / "logs" / "mcp_template_line_eval" / "report.json")
    parser.add_argument("--markdown", type=Path, default=repo_root / "logs" / "mcp_template_line_eval" / "report.md")
    args = parser.parse_args()
    if args.reclassify_report:
        prior = json.loads(args.reclassify_report.read_text(encoding="utf-8"))
        current_rows = {row["case_id"]: row for row in parse_template(args.template, args.catalog)}
        rescored = []
        for old in prior.get("rows") or []:
            current = current_rows.get(old.get("case_id"))
            row = refresh_checkpoint_metadata(dict(old), current)
            if current and current.get("source_status") == "skipped":
                row["status"] = "skipped"
                row["comparison"] = None
                row["skip_reason"] = current.get("skip_reason")
                rescored.append(row)
            else:
                rescored.append(recompare_checkpoint_row(row))
        report = {
            "schema": SCHEMA,
            "evaluation_id": EVALUATION_ID,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "mode": "offline_reclassification",
            "retry_policy": "none",
            "source_report": str(args.reclassify_report),
            "rows": rescored,
        }
        report["summary"] = build_summary(rescored)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        write_markdown(args.markdown, report)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        return 0
    if args.execute == args.list_only:
        parser.error("必须且只能选择 --list-only 或 --execute")

    template_rows = parse_template(args.template.resolve(), args.catalog.resolve())
    selected = [row for row in template_rows if not args.section or args.section.casefold() in row["section"].casefold()]
    if args.list_only:
        report = {
            "schema": SCHEMA,
            "evaluation_id": EVALUATION_ID,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "mode": "list_only",
            "template": str(args.template.resolve()),
            "template_sha256": sha256_text(args.template.read_text(encoding="utf-8")),
            "rows": [{**row, "status": row["source_status"], "request_count": 0} for row in selected],
        }
        report["summary"] = build_summary(report["rows"])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(args.markdown, report)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        return 0

    prior = load_checkpoint(args.checkpoint) if args.resume else []
    if not args.resume and args.checkpoint.exists():
        raise SystemExit(f"checkpoint already exists: {args.checkpoint}; use --resume or choose another path")
    current_by_case = {row["case_id"]: row for row in selected}
    prior = [
        recompare_checkpoint_row(refresh_checkpoint_metadata(row, current_by_case.get(row.get("case_id"))))
        for row in prior
    ]
    if args.resume and prior:
        rewrite_checkpoint(args.checkpoint, prior)
    by_case = {row["case_id"]: row for row in prior}
    runner = import_runner(repo_root)
    ready_sequence = [row for row in selected if row["source_status"] in {"ready", "duplicate"}]
    if args.case_id:
        requested_case_ids = set(args.case_id)
        unknown_case_ids = sorted(requested_case_ids - {row["case_id"] for row in ready_sequence})
        if unknown_case_ids:
            raise SystemExit(f"unknown or non-executable case id: {', '.join(unknown_case_ids)}")
        ready_sequence = [row for row in ready_sequence if row["case_id"] in requested_case_ids]
    ready_sequence = ready_sequence[max(0, args.start - 1):]
    live_budget = args.limit if args.limit > 0 else 10**9
    live_count = 0
    for row in selected:
        if row["case_id"] in by_case:
            continue
        output_row = {**row, "request_count": 0}
        if row["source_status"] == "skipped":
            output_row["status"] = row["source_status"] if row["source_status"] != "ready" else "not_selected"
            append_checkpoint(args.checkpoint, output_row)
            by_case[row["case_id"]] = output_row
            continue
        if row not in ready_sequence:
            continue
        if row["source_status"] == "duplicate":
            source = by_case.get(str(row.get("duplicate_of") or ""))
            output_row["status"] = "duplicate_reused" if source else "duplicate_source_unavailable"
            output_row["reused_result"] = source
            append_checkpoint(args.checkpoint, output_row)
            by_case[row["case_id"]] = output_row
            continue
        if live_count >= live_budget:
            continue
        try:
            raw = runner(args.url, row["prompt"], args.timeout)
            comparison = compare_row(row, raw)
            output_row.update(comparison)
            output_row["raw"] = raw
            output_row["request_count"] = 1
            output_row["status"] = "passed" if comparison["comparison"]["overall_passed"] else "failed"
        except Exception as exc:  # no retry by contract
            output_row["request_count"] = 1
            output_row["status"] = "error"
            output_row["error"] = f"{type(exc).__name__}: {exc}"
        live_count += 1
        append_checkpoint(args.checkpoint, output_row)
        by_case[row["case_id"]] = output_row
        print(json.dumps({"case_id": row["case_id"], "line": row["source_line"], "status": output_row["status"], "live_count": live_count}, ensure_ascii=False), flush=True)

    ordered = [by_case.get(row["case_id"], {**row, "status": "not_selected", "request_count": 0}) for row in selected]
    report = {
        "schema": SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "execute",
        "retry_policy": "none",
        "template": str(args.template.resolve()),
        "template_sha256": sha256_text(args.template.read_text(encoding="utf-8")),
        "url": args.url,
        "rows": ordered,
    }
    report["summary"] = build_summary(ordered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    write_markdown(args.markdown, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if report["summary"]["overall_passed"] == report["summary"]["executed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
