from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client


MCP_DIR = Path(__file__).resolve().parent
SERVER_FILE = MCP_DIR / "bf_data_mcp_server.py"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://10.30.220.12:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("BF_LLM_MODEL", "chiqiong-blast-furnace:latest"))
MAX_TOOL_ROUNDS = int(os.getenv("BF_MCP_MAX_TOOL_ROUNDS", "6"))


SYSTEM_PROMPT = (
    "你是冀南钢铁 GL02 高炉数据助手。"
    "涉及实时值、历史值、变量点位、报表事实时，必须调用工具查询，不得编造。"
    "默认高炉范围是 \\冀南钢铁\\SIO\\GL02，不得混用 \\冀南二期\\EQ\\SI0\\GL02。"
    "如果变量 status 是 available_substitute、derived、derived_substitute，回答中必须说明替代或派生口径。"
    "如果 confidence 不是 high，回答中必须说明置信等级。"
    "如果工具返回无数据或变量缺失，必须明确说明，不得补造数值。"
    "最终回答尽量包含变量名、短名、点ID、描述、时间戳、数值、质量码和数据源。"
)


def mcp_tool_to_ollama_tool(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        },
    }


def mcp_result_to_text(result: Any) -> str:
    structured = getattr(result, "structuredContent", None)
    if structured:
        return json.dumps(structured, ensure_ascii=False, default=str)
    parts = []
    for content in result.content:
        if isinstance(content, types.TextContent):
            parts.append(content.text)
        else:
            parts.append(str(content))
    return "\n".join(parts)


def ollama_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
    }
    if tools:
        payload["tools"] = tools
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    calls = message.get("tool_calls") or []
    normalized = []
    for call in calls:
        fn = call.get("function") or {}
        name = fn.get("name") or call.get("name")
        args = fn.get("arguments") or call.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if name:
            normalized.append({"name": name, "arguments": args})
    return normalized


async def ask(session: ClientSession, user_text: str) -> str:
    tools_response = await session.list_tools()
    tools = [mcp_tool_to_ollama_tool(tool) for tool in tools_response.tools]
    tool_names = {tool.name for tool in tools_response.tools}
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        response = ollama_chat(messages, tools)
        message = response.get("message") or {}
        messages.append(message)
        tool_calls = normalize_tool_calls(message)
        if not tool_calls:
            return message.get("content") or ""

        for tool_call in tool_calls:
            name = tool_call["name"]
            args = tool_call["arguments"]
            if name not in tool_names:
                result_text = json.dumps({"ok": False, "error": "UNKNOWN_TOOL", "tool": name}, ensure_ascii=False)
            else:
                result = await session.call_tool(name, args)
                result_text = mcp_result_to_text(result)
            messages.append({"role": "tool", "name": name, "content": result_text})

    return "工具调用轮数超过上限，请缩小问题范围或明确变量名。"


async def main() -> None:
    env = dict(os.environ)
    server_params = StdioServerParameters(
        command=os.getenv("BF_MCP_PYTHON", "python"),
        args=[str(SERVER_FILE)],
        env=env,
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("冀南钢铁 GL02 Ollama + MCP 数据助手已启动。输入 exit 退出。")
            while True:
                user_text = input("\n用户> ").strip()
                if user_text.lower() in {"exit", "quit", "q"}:
                    break
                answer = await ask(session, user_text)
                print(f"\n助手> {answer}")


if __name__ == "__main__":
    asyncio.run(main())


