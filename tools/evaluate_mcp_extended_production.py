from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


TECHNICAL_UNDERSCORE_ID = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+(?![A-Za-z0-9_])"
)


def spoken_prompt_technical_ids(prompt: str, canonical_ids: set[str]) -> list[str]:
    """Return internal point identifiers that make a user prompt non-colloquial.

    Standalone A-H letters are allowed as physical position labels, for example
    ``顶温 A 点`` or ``7 层 B 点``. Canonical object IDs and underscore-shaped
    technical identifiers remain forbidden in spoken prompts.
    """

    text = str(prompt or "")
    found = set(TECHNICAL_UNDERSCORE_ID.findall(text))
    for object_id in canonical_ids:
        token = str(object_id or "").strip()
        if not token or (len(token) == 1 and token.upper() in set("ABCDEFGH")):
            continue
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text, flags=re.I):
            found.add(token)
    return sorted(found, key=lambda value: (value.casefold(), value))


def validate_spoken_prompt_policy(spec: dict[str, Any], cases: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    """Validate the Chinese-semantics-only prompt contract before any request."""

    if spec.get("prompt_policy") != "chinese_semantics_only_allow_position_letters_A_to_H":
        return []
    catalog_path = root / str(spec["source_catalog"])
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    canonical_ids = {
        str(item.get("object_id") or "").strip()
        for item in catalog.get("objects") or []
        if str(item.get("object_id") or "").strip()
    }
    violations = []
    for case in cases:
        identifiers = spoken_prompt_technical_ids(case["prompt"], canonical_ids)
        if identifiers:
            violations.append({"case_id": case["case_id"], "technical_ids": identifiers})
    return violations


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return round(ordered[index], 1)


def load_cases(spec_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for variable in spec["variables"]:
        for template in spec["templates"]:
            cases.append({
                "case_id": f"EXT-{variable['object_id']}-{template['template_id']}",
                "object_id": variable["object_id"],
                "label": variable["label"],
                "template_id": template["template_id"],
                "query_type": template["query_type"],
                "prompt": template["prompt"].format(**variable),
            })
    return spec, cases


def find_sensor_payload(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    for event in raw.get("tool_results") or []:
        if str(event.get("tool") or "") != "query_gl02_sensors":
            continue
        payload = event.get("result") or {}
        items = payload.get("items") or []
        return payload, items[0] if items and isinstance(items[0], dict) else None
    return None, None


def score_case(case: dict[str, Any], raw: dict[str, Any]) -> dict[str, bool]:
    starts = [item for item in raw.get("tool_starts") or [] if isinstance(item, dict)]
    sensor_starts = [item for item in starts if str(item.get("tool") or "") == "query_gl02_sensors"]
    payload, item = find_sensor_payload(raw)
    answer = str(raw.get("answer") or "")
    folded = answer.casefold()
    expected_id = case["object_id"]
    expected_type = case["query_type"]
    arguments_ok = any(
        expected_id in (start.get("arguments") or {}).get("variables", [])
        and str((start.get("arguments") or {}).get("query_type") or "") == expected_type
        for start in sensor_starts
    )
    checks = {
        "request_ok": bool(raw.get("ok")) and "final" in (raw.get("events") or []),
        "one_sensor_call": len(sensor_starts) == 1 and len(starts) == 1,
        "arguments_exact": arguments_ok,
        "tool_result_ok": bool(payload and payload.get("ok") and item and item.get("ok")),
        "object_fidelity": expected_id.casefold() in folded,
        "time_present": "时间" in answer,
        "source_present": "来源" in answer,
        "unit_present": any(token in answer for token in ("kPa", "℃", "%", "m", "t/h", "m³/min", "单位未登记", "无量纲")),
        "no_unverified_fabrication": "实时数据库未核实" not in answer,
    }
    if expected_type == "latest":
        checks.update({
            "quality_present": "质量" in answer,
            "value_present": any(char.isdigit() for char in answer),
        })
    else:
        required = ("样本数", "均值", "标准差", "极差", "首值", "末值", "变化量", "斜率", "趋势", "CV")
        checks["statistics_complete"] = all(token in answer for token in required)
        stats = (item or {}).get("statistics") or {}
        avg = stats.get("avg")
        stddev = stats.get("stddev")
        if isinstance(avg, (int, float)) and isinstance(stddev, (int, float)) and avg:
            cv = float(stddev) / float(avg) * 100.0
            checks["cv_recomputable"] = math.isfinite(cv) and "CV" in answer
        else:
            checks["cv_recomputable"] = "不可计算" in answer or "缺失" in answer
    return checks


def execute_case(case: dict[str, Any], url: str, timeout: int, root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(root / "tools"))
    from probe_8093_cross_mcp_computation import run_once

    raw = run_once(url, case["prompt"], timeout, session_state={})
    checks = score_case(case, raw)
    return {
        **case,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "raw": raw,
        "automatic_retries": 0,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# MCP 扩展生产回归", "",
        f"> 目标：`{report['target']}`  ",
        f"> 用例：`{report['summary']['cases']}`  ",
        "> 自动重试：`0`", "",
        "| 用例 | 点位 | 类型 | 状态 | 失败检查 | 耗时(ms) |",
        "|---|---|---|---|---|---:|",
    ]
    for row in report["rows"]:
        failed = "、".join(key for key, value in row["checks"].items() if not value) or "—"
        lines.append(
            f"| `{row['case_id']}` | `{row['object_id']}` | `{row['template_id']}` | "
            f"`{row['status']}` | {failed} | {row.get('raw', {}).get('elapsed_ms', '—')} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--spec", type=Path, default=root / "PT" / "智能体工具能力扩展生产回归.v1.json")
    parser.add_argument("--url", default="http://10.30.220.12:8093/api/qa/chat")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--checkpoint", type=Path, default=root / "logs" / "mcp_extended" / "checkpoint.jsonl")
    parser.add_argument("--output", type=Path, default=root / "logs" / "mcp_extended" / "report.json")
    parser.add_argument("--markdown", type=Path, default=root / "logs" / "mcp_extended" / "report.md")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args()
    spec, cases = load_cases(args.spec)
    prompt_violations = validate_spoken_prompt_policy(spec, cases, root)
    if prompt_violations:
        print(json.dumps({"ok": False, "error": "spoken_prompt_contains_technical_id", "violations": prompt_violations}, ensure_ascii=False, indent=2))
        return 3
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case["case_id"] in selected]
    if args.list_only:
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        return 0
    rows: list[dict[str, Any]] = []
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(execute_case, case, args.url, args.timeout, root): case for case in cases}
        for future in as_completed(futures):
            case = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {**case, "status": "error", "error": f"{type(exc).__name__}: {exc}", "checks": {}, "automatic_retries": 0}
            rows.append(row)
            with args.checkpoint.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    rows.sort(key=lambda item: item["case_id"])
    latencies = [float(row.get("raw", {}).get("elapsed_ms")) for row in rows if row.get("raw", {}).get("elapsed_ms") is not None]
    report = {
        "schema": "bf.agent-tool-extended-production-report.v1",
        "requirement_id": spec["requirement_id"],
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": args.url,
        "retry_policy": "none",
        "concurrency": args.concurrency,
        "rows": rows,
        "summary": {
            "cases": len(rows),
            "passed": sum(row["status"] == "passed" for row in rows),
            "failed": sum(row["status"] == "failed" for row in rows),
            "errors": sum(row["status"] == "error" for row in rows),
            "p50_ms": round(statistics.median(latencies), 1) if latencies else None,
            "p95_ms": percentile(latencies, 0.95),
            "request_count": sum(int(row.get("raw", {}).get("request_count") or 0) for row in rows),
            "automatic_retries": 0,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if report["summary"]["passed"] == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
