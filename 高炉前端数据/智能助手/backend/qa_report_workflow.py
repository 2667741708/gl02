"""Bounded list -> select -> read -> summary-excerpt workflow (QAOPT-R05).

Report contents are evidence, never executable instructions. The summary is
an extract of the report's own summary section; no model invents missing text.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import PurePosixPath
from typing import Any

VERSION = "qa-report-workflow-v1"


def build_report_plan(question: str) -> dict[str, Any] | None:
    text = re.sub(r'“[^”]*”|"[^"\n]*"|「[^」]*」', "", question)
    kind = next((kind for kind in ("日报", "周报", "月报", "时报") if kind in text), "")
    if not kind or not any(word in text for word in ("最近", "最新")) or not any(word in text for word in ("读一下", "读取", "概括", "总结", "摘要", "内容")):
        return None
    return {"version": VERSION, "report_type": kind, "list_arguments": {"report_type": kind, "limit": 20}, "max_chars": 10000}


def _path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ":" in value or ".." in path.parts or path.suffix.lower() not in {".md", ".txt"}:
        return ""
    return path.as_posix()


def select_report(payload: dict[str, Any], kind: str) -> dict[str, Any] | None:
    rows = payload.get("reports")
    if payload.get("ok") is not True or not isinstance(rows, list) or not rows:
        return None
    # list_recent_reports contract sorts descending by modified_at. Do not
    # guess a different report if its first result fails the type/path contract.
    first = rows[0]
    if not isinstance(first, dict) or not _path(first.get("report_path")) or kind not in str(first.get("report_path")):
        return None
    if not isinstance(first.get("modified_at"), str) or not first["modified_at"]:
        return None
    return {**first, "report_path": _path(first["report_path"])}


def summary_excerpt(text: str, max_chars: int = 2500) -> tuple[str, bool]:
    lines = text.splitlines()
    heading = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$")
    start, level = None, 0
    for index, line in enumerate(lines):
        match = heading.match(line)
        if match and any(word in match.group(2) for word in ("摘要", "总结", "概览", "要点", "结论")):
            start, level = index + 1, len(match.group(1))
            break
    if start is not None:
        end = len(lines)
        for index in range(start, len(lines)):
            match = heading.match(lines[index])
            if match and len(match.group(1)) <= level:
                end = index
                break
        content = "\n".join(lines[start:end]).strip()
        if content:
            return content[:max_chars], len(content) > max_chars
    # No summary section: show actual body; expressly avoid claiming this is
    # a complete synthesis or a source of current live furnace measurements.
    content = text.strip()
    return content[:max_chars], True


async def execute_report_plan(plan: dict[str, Any], *, available_tools: set[str], validate: Any, call: Any, on_start: Any, on_result: Any, max_calls: int) -> dict[str, Any]:
    trace, executed = [], 0
    async def run_step(step_id, name, args):
        nonlocal executed
        policy = validate(name, args) if name in available_tools else {"ok": False, "errors": ["tool_unavailable"]}
        item = {"round": 0, "route": "deterministic_report_read", "step_id": step_id, "tool": name, "arguments": args, "policy": policy}
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
        item["result"] = {"ok": payload.get("ok"), "error": payload.get("error")}
        trace.append(item)
        on_result(item, payload)
        return payload

    def outcome(answer, status, complete=False):
        return {"ok": True, "tool_used": executed > 0, "answer": answer, "report_status": status, "complete": complete,
                "tool_trace": trace, "answer_route": "deterministic_report_read", "model_request_count": 0,
                "grounding_status": "verified_report_excerpt" if status == "read" else "no_verified_report_content"}

    if max_calls < 2:
        return outcome("本轮预算不足以完成报表目录及正文读取，未发送工具请求。", "budget_blocked")
    listing = await run_step("list", "list_recent_reports", plan["list_arguments"])
    selected = select_report(listing, plan["report_type"])
    if selected is None:
        return outcome("未找到可确认的最近报表，或目录查询/路径合同失败；本轮没有读取正文，不能给出摘要。", "selection_failed")
    result = await run_step("read", "read_report_excerpt", {"report_path": selected["report_path"], "mode": "full", "max_chars": plan["max_chars"]})
    source = f"报表：{selected['report_path']}；最近按文件更新时间选择：{selected['modified_at']}。"
    if result.get("ok") is not True or _path(result.get("report_path")) != selected["report_path"] or not isinstance(result.get("content"), str) or not result["content"].strip():
        return outcome(source + "\n正文未成功读取或来源不匹配；目录不等于正文，无法生成摘要。", "read_failed")
    excerpt, shortened = summary_excerpt(result["content"])
    filtered = re.sub(r"```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)", "[代码块已按禁代码策略省略]", excerpt)
    shortened = shortened or filtered != excerpt
    excerpt = filtered
    # Current MCP truncated compares Unicode chars with file bytes, so it may
    # be a false positive for Chinese reports. Never silently call it complete.
    partial = shortened or result.get("truncated") is not False
    qualifier = "摘要/正文摘录（读取可能截断，不代表全文总结）" if partial else "报表摘要原文摘录"
    answer = source + f"\n{qualifier}：\n" + excerpt + "\n\n以上为该报表所述历史内容，不代表当前实时炉况；未执行任何写操作。"
    return outcome(answer, "read", not partial)
