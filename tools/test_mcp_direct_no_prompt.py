"""Direct MCP capability and latency test without LLM prompts or QA routing.

This script starts the MCP stdio server, calls exact tools with JSON arguments,
and records pure MCP latency. It does not call the 27B model, inject a system
prompt, run RAG, or use colloquial routing templates.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER = ROOT / "高炉前端数据" / "智能助手" / "mcp" / "bf_data_mcp_server.py"


def result_payload(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    texts = [getattr(item, "text", str(item)) for item in getattr(result, "content", []) or []]
    text = "\n".join(texts)
    try:
        return json.loads(text)
    except Exception:
        return {"text": text}


def cases() -> dict[str, tuple[str, dict[str, Any]]]:
    end = datetime.now().astimezone().replace(second=0, microsecond=0)
    start = end - timedelta(minutes=30)
    return {
        "catalog": (
            "search_business_objects",
            {"query": "铁水硅含量", "object_types": ["hot_metal_analysis"]},
        ),
        "latest": (
            "query_gl02_sensors",
            {"variables": ["P_top"], "query_type": "latest"},
        ),
        "statistics": (
            "query_gl02_sensors",
            {
                "variables": ["P_top", "DP_total"],
                "query_type": "statistics",
                "start_time": start.isoformat(timespec="seconds"),
                "end_time": end.isoformat(timespec="seconds"),
                "agg": "all",
            },
        ),
        "correlation_chart": (
            "plot_gl02_analysis",
            {
                "variables": ["P_top", "DP_total"],
                "start_time": start.isoformat(timespec="seconds"),
                "end_time": end.isoformat(timespec="seconds"),
                "analysis_type": "correlation_scatter",
                "title": "无Prompt模板MCP直连相关性测试",
            },
        ),
    }


def payload_ok(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("ok", True) is False:
        return False
    if payload.get("partial") is True or int(payload.get("failure_count") or 0) > 0:
        return False
    if isinstance(payload.get("errors"), list) and payload["errors"]:
        return False
    return True


async def run(server: Path, selected: list[str]) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=[str(server)], env=dict(os.environ))
    results = []
    started = time.perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_started = time.perf_counter()
            available = await session.list_tools()
            list_tools_ms = round((time.perf_counter() - tools_started) * 1000, 1)
            tool_names = {item.name for item in available.tools}
            for case_id in selected:
                tool, arguments = cases()[case_id]
                call_started = time.perf_counter()
                if tool not in tool_names:
                    payload = {"ok": False, "error": "UNKNOWN_TOOL", "tool": tool}
                else:
                    payload = result_payload(await session.call_tool(tool, arguments))
                elapsed_ms = round((time.perf_counter() - call_started) * 1000, 1)
                results.append(
                    {
                        "case_id": case_id,
                        "tool": tool,
                        "arguments": arguments,
                        "elapsed_ms": elapsed_ms,
                        "ok": payload_ok(payload),
                        "result": payload,
                    }
                )
    return {
        "mode": "direct_mcp_without_prompt_template",
        "llm_used": False,
        "qa_router_used": False,
        "rag_used": False,
        "server": str(server),
        "list_tools_ms": list_tools_ms,
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="无Prompt模板、无27B的MCP stdio直连能力与延迟测试。")
    parser.add_argument("--server", type=Path, default=DEFAULT_SERVER, help="MCP stdio server路径。")
    parser.add_argument(
        "--case",
        action="append",
        choices=tuple(cases()),
        help="指定测试用例，可重复；省略时运行全部。",
    )
    parser.add_argument("--output", type=Path, help="可选JSON报告路径。")
    args = parser.parse_args()
    selected = args.case or list(cases())
    report = asyncio.run(run(args.server.resolve(), selected))
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if all(item["ok"] for item in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
