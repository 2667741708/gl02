"""Read-only audit of the model's MCP tool selection.

The script exposes only registered IMES tool schemas to the configured model,
prints the structured tool call chosen by the model, and never executes the
selected tool.  It is intended to prove planning behaviour without exposing
chain-of-thought or permitting SQL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import ollama_proxy_server as proxy  # noqa: E402
from mcp_host.client_manager import McpClientManager  # noqa: E402
from mcp_host.domain_router import select_mcp_servers  # noqa: E402
from mcp_host.server_registry import load_server_registry  # noqa: E402


async def registered_tools_for_question(question: str) -> tuple[list[dict], tuple[str, ...]]:
    registry = load_server_registry(BACKEND / "mcp_host" / "server_registry.json")
    selection = select_mcp_servers(question, registry)
    manager = McpClientManager(registry, sys.executable)
    async with manager:
        await manager.attach(selection.server_ids)
        return manager.ollama_tools(), selection.server_ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--question",
        default="请查询2#20260805-065炉次的C、Si、Mn、P、S，并列出每个试样。",
    )
    args = parser.parse_args()
    registered_tools, selected_server_ids = asyncio.run(
        registered_tools_for_question(args.question)
    )
    tools = proxy.qa_mcp_planner_tools(args.question, registered_tools)
    response = proxy.call_ollama_chat_obj(
        [
            {
                "role": "system",
                "content": proxy.QA_MCP_BRIDGE_SYSTEM_PROMPT
                + "本次只输出下一步必要的结构化工具调用，不要回答结果。",
            },
            {"role": "user", "content": args.question},
        ],
        tools=tools,
        temperature=0,
        max_tokens=360,
    )
    message = dict(response.get("message") or {})
    payload = {
        "question": args.question,
        "selected_server_ids": list(selected_server_ids),
        "registered_tool_count": len(registered_tools),
        "planner_tool_count": len(tools),
        "registered_tool_names": [item["function"]["name"] for item in tools],
        "model_content": message.get("content") or response.get("response") or "",
        "model_tool_calls": proxy.normalize_tool_calls(message),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["model_tool_calls"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
