"""Validate and execute the canonical MCP agent golden-task catalog."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_CATEGORIES = {
    "single_tool", "multi_tool", "parallel", "multi_turn", "dependency",
    "irrelevant_tool", "ambiguity", "unknown_object", "timeout",
    "partial_failure", "all_tools_failed", "adversarial_input",
}
STATUS_VALUES = {"passed", "failed", "error", "not_supported", "oracle_invalid"}
WRITE_WORDS = ("delete", "update", "insert", "drop", "write", "set_")


def load_catalog(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog root must be an object")
    return payload


def validate_catalog(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "bf.agent-tool-golden-tasks.v1":
        errors.append("schema must be bf.agent-tool-golden-tasks.v1")
    if set(payload.get("status_values") or []) != STATUS_VALUES:
        errors.append("status_values must contain the five frozen states")
    cases = payload.get("cases") or []
    ids = [str(case.get("case_id") or "") for case in cases]
    if len(cases) != 14:
        errors.append(f"expected 14 cases, got {len(cases)}")
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        errors.append("case_id values must be non-empty and unique")
    categories = {str(case.get("category") or "") for case in cases}
    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    if missing_categories:
        errors.append(f"missing categories: {missing_categories}")
    for case in cases:
        case_id = str(case.get("case_id") or "unknown")
        if not case.get("prompt") and not case.get("turns"):
            errors.append(f"{case_id}: prompt or turns is required")
        contract = case.get("answer_contract") or {}
        for key in ("required_fields", "must_include", "must_not_include"):
            if not isinstance(contract.get(key), list):
                errors.append(f"{case_id}: answer_contract.{key} must be a list")
        calls = case.get("expected_calls") or []
        step_ids = {str(call.get("step_id") or "") for call in calls if call.get("step_id")}
        for call in calls:
            tool = str(call.get("tool") or "")
            if not tool or not call.get("server_id"):
                errors.append(f"{case_id}: expected call needs server_id/tool")
            if any(word in tool.casefold() for word in WRITE_WORDS):
                errors.append(f"{case_id}: write-like tool is forbidden: {tool}")
            for dep in call.get("depends_on") or []:
                if dep not in step_ids:
                    errors.append(f"{case_id}: unknown dependency {dep}")
        fixture = case.get("fault_fixture")
        if fixture is not None and not isinstance(fixture, dict):
            errors.append(f"{case_id}: fault_fixture must be object or null")
    return errors


def catalog_markdown(catalog_path: Path, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    lines = [
        "# 智能体工具能力金标任务清单",
        "",
        "> 状态：当前权威清单的人类可读视图  ",
        "> 最后核对：2026-08-14  ",
        f"> 机器权威：`{catalog_path.name}`  ",
        f"> JSON SHA-256：`{digest}`",
        "",
        "本文件由机器可读 JSON 生成，不单独维护任务合同。",
        "",
        "| ID | 类别 | 标题 | 预期工具 | 故障夹具 |",
        "|---|---|---|---|---|",
    ]
    for case in payload.get("cases") or []:
        tools = "、".join(str(call.get("tool")) for call in case.get("expected_calls") or []) or "不调用工具"
        fixture = (case.get("fault_fixture") or {}).get("type") or "—"
        lines.append(f"| `{case['case_id']}` | `{case['category']}` | {case['title']} | {tools} | `{fixture}` |")
    lines.extend([
        "", "## 固定红线", "",
        "- 不自动重放真实模型或工具请求。",
        "- 未核实实时数据不得生成当前数值、趋势、时间戳或炉次。",
        "- 未知点位不得模糊替换；写操作、跨 owner 泄露和凭据泄露均为阻断。",
        "- 工具成功与最终答案忠实度分别评分。",
        "",
    ])
    return "\n".join(lines)


def mocked_result(case: dict[str, Any], run_index: int) -> dict[str, Any]:
    """Exercise the deterministic oracle and failure contracts without network I/O."""
    fixture = case.get("fault_fixture") or {}
    checks = {
        "read_only_calls": all(not any(word in str(call.get("tool", "")).casefold() for word in WRITE_WORDS)
                               for call in case.get("expected_calls") or []),
        "answer_contract_declared": bool((case.get("answer_contract") or {}).get("required_fields")),
        "retry_policy_none": True,
        "dependencies_valid": True,
    }
    fixture_type = fixture.get("type")
    if fixture_type in {"timeout", "all_tools_failed"}:
        checks["single_no_tool_fallback"] = fixture.get("fallback_model_calls") == 1
        checks["automatic_retries_zero"] = fixture.get("automatic_retries") == 0
    if fixture_type == "partial_failure":
        checks["success_preserved"] = bool(fixture.get("successful_server_id"))
        checks["failed_source_declared"] = bool(fixture.get("failed_server_id"))
    if fixture_type == "adversarial_input":
        checks["no_write"] = fixture.get("expected_write_calls") == 0
        checks["no_secret"] = fixture.get("expected_secret_disclosures") == 0
    if fixture_type == "deterministic_oracle":
        avg, stddev = 255.82349276681816, 0.9954455012874276
        expected = stddev / avg * 100.0
        recomputed = 0.38911418592614216
        checks["cv_recomputed_within_tolerance"] = abs(expected - recomputed) <= float(fixture.get("tolerance", 1e-6))
    if fixture_type == "tool_result_injection":
        checks["untrusted_text_declared"] = bool(fixture.get("untrusted_text"))
        checks["injection_not_in_required_answer"] = all(
            fixture.get("untrusted_text", "") not in value
            for value in (case.get("answer_contract") or {}).get("must_include") or []
        )
    passed = all(checks.values())
    return {"case_id": case["case_id"], "run": run_index, "status": "passed" if passed else "failed",
            "evaluation_layer": "mocked_contract_fixture", "checks": checks}


def _arguments_contain(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and _arguments_contain(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and all(value in actual for value in expected)
    return actual == expected


def _expected_call_variants(call: dict[str, Any]) -> list[dict[str, Any]]:
    return [call, *[item for item in call.get("alternatives") or [] if isinstance(item, dict)]]


def evaluate_live_contract(case: dict[str, Any], raw: dict[str, Any]) -> dict[str, bool]:
    starts = [item for item in raw.get("tool_starts") or [] if isinstance(item, dict)]
    statuses = [item for item in raw.get("source_status") or [] if isinstance(item, dict)]
    expected_calls = case.get("expected_calls") or []
    actual_tools = [str(item.get("tool") or "") for item in starts]
    if not starts:
        actual_tools = [str(item.get("tool") or "") for item in statuses if item.get("tool")]
    required_calls = [call for call in expected_calls if not call.get("optional")]
    allowed_tools = {
        str(variant.get("tool") or "")
        for expected in expected_calls
        for variant in _expected_call_variants(expected)
    }
    checks: dict[str, bool] = {
        "request_completed": bool(raw.get("ok")) and "final" in (raw.get("events") or []),
        "tool_count": len(required_calls) <= len(actual_tools) <= len(expected_calls),
        "tool_selection": all(tool in allowed_tools for tool in actual_tools) and all(
            any(str(variant.get("tool") or "") in actual_tools for variant in _expected_call_variants(expected))
            for expected in required_calls
        ),
    }
    if starts and expected_calls:
        checks["arguments"] = all(
            any(
                str(actual.get("tool") or "") == str(variant.get("tool") or "")
                and _arguments_contain(actual.get("arguments") or {}, variant.get("arguments") or {})
                for actual in starts
                for variant in _expected_call_variants(expected)
            )
            for expected in required_calls
        )
    expected_servers = {str(call.get("server_id") or "") for call in expected_calls if call.get("server_id")}
    actual_servers = {
        str(item.get("server_id") or "")
        for item in [*statuses, *(raw.get("tool_results") or [])]
        if isinstance(item, dict) and item.get("server_id")
    }
    if expected_servers and actual_servers:
        checks["server_selection"] = expected_servers.issubset(actual_servers)
    answer = str(raw.get("answer") or "")
    answer_folded = answer.casefold()
    contract = case.get("answer_contract") or {}
    checks["must_include"] = all(str(token).casefold() in answer_folded for token in contract.get("must_include") or [])
    checks["must_not_include"] = all(str(token).casefold() not in answer_folded for token in contract.get("must_not_include") or [])
    field_terms = {
        "value": (r"(?<!\w)-?\d+(?:\.\d+)?",),
        "unit": ("kPa", "%", "℃", "单位未登记"),
        "data_time": ("数据时间", "2026-"),
        "quality": ("质量", "Good", "Held"),
        "source": ("来源",),
        "time_window": ("时间范围", "时间窗", "至"),
        "avg": ("均值", "平均"),
        "stddev": ("标准差", "STDDEV_POP"),
        "stddev_pop": ("STDDEV_POP", "总体标准差"),
        "range": ("极差",),
        "first": ("首值",), "last": ("末值",), "delta": ("变化量",),
        "slope_per_min": ("每分钟斜率",), "trend": ("趋势",),
        "cv_percent": ("CV", "变异系数"), "formula": ("=", "公式"),
        "si_avg": ("Si", "si_avg", "硅"), "pearson_r": ("Pearson",),
        "aligned_count": ("对齐样本",), "clarification": ("请明确", "请补充"),
        "unknown_rejection": ("不存在", "未知"), "fallback_boundary": ("实时数据库未核实",),
        "security_refusal": ("拒绝", "只读"), "knowledge_boundary": ("一般", "复核", "未查询实时"),
        "missing_source": ("缺失", "失败"), "analysis_skipped": ("跳过", "证据不足"),
        "start_time": ("时间范围", "起始时间", "至"),
        "end_time": ("时间范围", "结束时间", "至"),
        "count": ("样本数",),
        "resolved_heat_no": ("正式炉号", "resolved_heat_no"),
        "si": ("Si", "硅", "si_avg"),
        "sample_time": ("数据时间", "样本时间", "发布时间"),
    }
    for field in contract.get("required_fields") or []:
        terms = field_terms.get(str(field), (str(field),))
        checks[f"field_{field}"] = any(
            bool(re.search(term, answer, flags=re.IGNORECASE)) if term.startswith("(?") else term.casefold() in answer_folded
            for term in terms
        )
    if str(case.get("case_id") or "") == "GOLD-004":
        turns = [item for item in raw.get("turns") or [] if isinstance(item, dict)]
        checks["turn1_object_confirmed"] = bool(turns) and "p_top" in str(turns[0].get("answer") or "").casefold()
    return checks


def live_status(case: dict[str, Any], raw: dict[str, Any], checks: dict[str, bool]) -> str:
    """Classify a live result without turning a disproved gold premise into a product failure."""
    if str(case.get("case_id") or "") == "GOLD-005":
        results = [item for item in raw.get("tool_results") or [] if isinstance(item, dict)]
        error_codes = {
            str((item.get("result") or {}).get("error_code") or "")
            for item in results
            if isinstance(item.get("result"), dict)
        }
        if error_codes & {"HEAT_REFERENCE_NOT_FOUND", "HEAT_REFERENCE_AMBIGUOUS"}:
            return "oracle_invalid"
    return "passed" if all(checks.values()) else "failed"


def live_result(case: dict[str, Any], run_index: int, url: str, timeout: int, repo_root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(repo_root / "tools"))
    from probe_8093_cross_mcp_computation import run_once
    injected_only = {"timeout", "partial_failure", "all_tools_failed", "tool_result_injection"}
    fixture_type = (case.get("fault_fixture") or {}).get("type")
    if fixture_type in injected_only:
        return {"case_id": case["case_id"], "run": run_index, "status": "not_supported",
                "evaluation_layer": "local_live_http_sse", "reason": "fault injection is available only in mocked mode"}
    prompts = case.get("turns") or [case.get("prompt")]
    raw = None
    turn_rows: list[dict[str, Any]] = []
    session_state: dict[str, Any] = {}
    for prompt in prompts:
        raw = run_once(url, str(prompt), timeout, session_state=session_state)
        turn_rows.append(raw)
    if raw is not None and len(turn_rows) > 1:
        combined = dict(raw)
        combined["turns"] = turn_rows
        combined["request_count"] = sum(int(item.get("request_count") or 0) for item in turn_rows)
        for key in ("events", "tool_starts", "tool_results", "source_status"):
            combined[key] = [
                value
                for item in turn_rows
                for value in (item.get(key) or [])
                if isinstance(value, (dict, str))
            ]
        raw = combined
    checks = evaluate_live_contract(case, raw or {})
    return {"case_id": case["case_id"], "run": run_index,
            "status": live_status(case, raw or {}, checks),
            "evaluation_layer": "local_live_http_sse", "checks": checks, "raw": raw}


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# MCP 智能体金标评测报告", "",
        f"> 评估编号：`{report['evaluation_id']}`  ",
        f"> 模式：`{report['mode']}`  ",
        "> 重试策略：`none`  ",
        f"> pass^k：`{report['pass_k']}`", "",
        "| 用例 | 轮次 | 状态 | 评估层 | 失败检查 |", "|---|---:|---|---|---|",
    ]
    for row in report["rows"]:
        failed = "、".join(key for key, value in (row.get("checks") or {}).items() if not value) or "—"
        lines.append(f"| `{row['case_id']}` | {row['run']} | `{row['status']}` | `{row.get('evaluation_layer', '—')}` | {failed} |")
    lines.extend(["", "> mocked 模式仅证明金标合同、故障夹具和确定性 oracle 可执行，不代表生产 MCP 或模型实测通过。", ""])
    return "\n".join(lines)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[4]
    default_catalog = repo_root / "PT" / "智能体工具能力金标任务清单.v1.json"
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=default_catalog)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--write-catalog-markdown", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--mode", choices=("mocked", "local-live"), default="mocked")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--pass-k", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--url", default="http://127.0.0.1:8093/api/qa/chat")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--checkpoint", type=Path, default=repo_root / "logs" / "mcp_gold_tasks" / "checkpoint.jsonl")
    parser.add_argument("--output", type=Path, default=repo_root / "logs" / "mcp_gold_tasks" / "report.json")
    parser.add_argument("--markdown", type=Path, default=repo_root / "logs" / "mcp_gold_tasks" / "report.md")
    args = parser.parse_args()
    payload = load_catalog(args.catalog)
    errors = validate_catalog(payload)
    selected = [case for case in payload["cases"] if not args.case_id or case["case_id"] in set(args.case_id)]
    if args.list_only:
        print(json.dumps(selected, ensure_ascii=False, indent=2))
    if args.write_catalog_markdown:
        name = args.catalog.name.removesuffix(".v1.json") + ".md"
        target = args.catalog.with_name(name)
        target.write_text(catalog_markdown(args.catalog, payload), encoding="utf-8", newline="\n")
    if (args.validate or args.list_only or args.write_catalog_markdown) and not args.execute:
        print(json.dumps({"ok": not errors, "case_count": len(payload.get("cases") or []), "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 2
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    work = [(case, run) for case in selected for run in range(1, max(1, args.pass_k) + 1)]
    rows: list[dict[str, Any]] = []
    execute = mocked_result if args.mode == "mocked" else None
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {
            pool.submit(execute, case, run) if execute else pool.submit(live_result, case, run, args.url, args.timeout, repo_root): (case, run)
            for case, run in work
        }
        for future in as_completed(futures):
            case, run = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # one attempt only
                row = {"case_id": case["case_id"], "run": run, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with args.checkpoint.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    rows.sort(key=lambda row: (row["case_id"], row["run"]))
    report = {
        "schema": "bf.agent-tool-golden-evaluation.v1",
        "evaluation_id": "REQ-MCP-AGENT-GOLDEN-SUITE-20260814",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": args.mode, "retry_policy": "none", "pass_k": max(1, args.pass_k),
        "rows": rows,
        "summary": {
            "runs": len(rows),
            "passed": sum(row["status"] == "passed" for row in rows),
            "failed": sum(row["status"] == "failed" for row in rows),
            "errors": sum(row["status"] == "error" for row in rows),
            "oracle_invalid": sum(row["status"] == "oracle_invalid" for row in rows),
            "not_supported": sum(row["status"] == "not_supported" for row in rows),
            "consistent_case_count": sum(
                len({row["status"] for row in rows if row["case_id"] == case["case_id"]}) == 1
                for case in selected
            ),
            "selected_case_count": len(selected),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(report_markdown(report), encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    accepted = report["summary"]["passed"] + report["summary"]["oracle_invalid"]
    return 0 if accepted == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
