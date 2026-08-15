"""Probe two-round MCP planning without executing any MCP data tool."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import ollama_proxy_server as proxy  # noqa: E402


FIND_TOOL = {
    "type": "function",
    "function": {
        "name": "find_gl02_variables",
        "description": "按中文口语、别名、变量名或点位检索GL02变量。",
        "parameters": {
            "type": "object",
            "required": ["keyword"],
            "properties": {"keyword": {"type": "string"}, "limit": {"type": "integer"}},
        },
    },
}
QUERY_TOOL = {
    "type": "function",
    "function": {
        "name": "query_gl02_sensors",
        "description": "按标准变量名批量查询GL02传感器。",
        "parameters": {
            "type": "object",
            "required": ["variables"],
            "properties": {
                "variables": {"type": "array", "items": {"type": "string"}},
                "query_type": {"type": "string", "enum": ["latest", "history", "statistics"]},
            },
        },
    },
}


def call(messages):
    response = proxy.call_ollama_chat_obj(messages, tools=[FIND_TOOL, QUERY_TOOL], temperature=0, max_tokens=360)
    message = dict(response.get("message") or {})
    return message, proxy.normalize_tool_calls(message)


def main() -> int:
    system = {
        "role": "system",
        "content": proxy.QA_MCP_BRIDGE_SYSTEM_PROMPT
        + "本测试只输出下一步必要工具调用。用户要求先查目录时必须先调用find_gl02_variables，收到结果后再调用query_gl02_sensors。",
    }
    user = {"role": "user", "content": "先从目录确认‘A点顶压’对应的标准变量，然后查询其当前值。"}
    first_message, first_calls = call([system, user])
    if not first_calls:
        print(json.dumps({"ok": False, "stage": "first", "calls": []}, ensure_ascii=False, indent=2))
        return 2
    first_call = first_calls[0]
    tool_result = {
        "ok": True,
        "matches": [
            {
                "variable_name": "P_top_A",
                "aliases": ["顶压A", "A点顶压", "A点上升管煤气压力"],
                "point_id": "\\冀南钢铁\\SIO\\GL02\\LD\\SIO_GL02_LD_T0067",
                "score": 1.0,
            }
        ],
    }
    assistant = {
        "role": "assistant",
        "content": first_message.get("content") or "",
        "tool_calls": [
            {"function": {"name": first_call["name"], "arguments": first_call["arguments"]}}
        ],
    }
    tool = {
        "role": "tool",
        "name": first_call["name"],
        "content": json.dumps(tool_result, ensure_ascii=False),
    }
    _, second_calls = call([system, user, assistant, tool])
    payload = {
        "ok": bool(
            first_call.get("name") == "find_gl02_variables"
            and second_calls
            and second_calls[0].get("name") == "query_gl02_sensors"
            and second_calls[0].get("arguments", {}).get("variables") == ["P_top_A"]
        ),
        "first_round_calls": first_calls,
        "second_round_calls": second_calls,
        "mcp_data_executed": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
