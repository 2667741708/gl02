"""Run one compact automatic-routing audit against the production 8093 MCP host."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from verify_8093_assistant_sse_once import get_json, run_sse


def status_url_for_chat(chat_url: str) -> str:
    parsed = urlparse(chat_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid chat URL: {chat_url}")
    return f"{parsed.scheme}://{parsed.netloc}/api/ollama/status"


def trace_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for item in items:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        summaries.append(
            {
                "round": item.get("round"),
                "route": item.get("route"),
                "server_id": item.get("server_id"),
                "tool": item.get("tool"),
                "arguments": item.get("arguments") or {},
                "cache_hit": item.get("cache_hit"),
                "result_ok": result.get("ok"),
                "result_keys": list(result)[:20],
                "source_objects": result.get("source_objects") or [],
                "current_heat_no": result.get("current_heat_no"),
                "previous_heat_no": result.get("previous_heat_no"),
                "error": result.get("error") or result.get("error_code"),
            }
        )
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit one colloquial cross-database MCP query on 8093.")
    parser.add_argument("--url", default="http://10.30.220.12:8093/api/qa/chat")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--question", required=True)
    args = parser.parse_args()

    status_url = status_url_for_chat(args.url)
    status_before = get_json(status_url, 20)
    sse = run_sse(args.url, args.question, args.timeout, use_mcp_tools=None)
    status_after = get_json(status_url, 20)
    trace = [item for item in sse.get("mcp_tool_trace") or [] if isinstance(item, dict)]
    servers = list(dict.fromkeys(str(item.get("server_id") or "") for item in trace if item.get("server_id")))
    tools = list(dict.fromkeys(str(item.get("tool") or "") for item in trace if item.get("tool")))
    output = {
        "schema": "ops.8093.cross-database-mcp-audit.v1",
        "ok": True,
        "question": args.question,
        "runtime_before_ok": bool(status_before.get("ok")),
        "runtime_after_ok": bool(status_after.get("ok")),
        "prepared_mcp_tool_calling": sse.get("prepared_mcp_tool_calling"),
        "servers": servers,
        "tools": tools,
        "cross_service": len(servers) >= 2,
        "tool_trace": trace_summary(trace),
        "first_delta_ms": sse.get("first_delta_ms"),
        "total_ms": sse.get("total_ms"),
        "answer": sse.get("answer"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
