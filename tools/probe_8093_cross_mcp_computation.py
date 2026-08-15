"""Run exactly one authenticated guest SSE request for a cross-MCP computation audit."""
from __future__ import annotations

import argparse
import http.client
import json
import math
import re
import sys
import time
from typing import Any
from urllib.parse import urlparse


def open_connection(parsed, timeout: int):
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    return connection_type(parsed.hostname, parsed.port, timeout=timeout)


def bootstrap(base_url: str, timeout: int) -> tuple[str, dict[str, Any]]:
    parsed = urlparse(base_url)
    connection = open_connection(parsed, timeout)
    connection.request(
        "GET",
        "/api/qa/bootstrap",
        headers={"Accept": "application/json", "Cache-Control": "no-cache"},
    )
    response = connection.getresponse()
    body = response.read()
    cookie_headers = response.getheaders()
    connection.close()
    if response.status != 200:
        raise RuntimeError(f"bootstrap HTTP {response.status}: {body[:1000]!r}")
    cookies = []
    for name, value in cookie_headers:
        if name.lower() == "set-cookie":
            cookies.append(value.split(";", 1)[0])
    return "; ".join(cookies), json.loads(body.decode("utf-8", errors="replace"))


def run_once(
    url: str,
    question: str,
    timeout: int,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    state = session_state if session_state is not None else {}
    if state.get("conversation_id"):
        cookie = str(state.get("cookie") or "")
        bootstrap_payload = dict(state.get("bootstrap_payload") or {})
        conversation_id = state.get("conversation_id")
    else:
        cookie, bootstrap_payload = bootstrap(base_url, min(timeout, 30))
        conversation = bootstrap_payload.get("conversation") or {}
        conversation_id = conversation.get("id")
        state.update({"cookie": cookie, "bootstrap_payload": bootstrap_payload, "conversation_id": conversation_id})
    if not conversation_id:
        raise RuntimeError("bootstrap did not return conversation.id")
    body = json.dumps(
        {
            "conversation_id": conversation_id,
            "message": question,
            "stream": True,
            "use_mcp_tools": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    connection = open_connection(parsed, timeout)
    started = time.perf_counter()
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "text/event-stream",
        "Origin": base_url,
        "X-BF-Acceptance-ID": "Q-8093-CROSS-MCP-COMPUTATION-20260813",
    }
    if cookie:
        headers["Cookie"] = cookie
    connection.request(
        "POST",
        parsed.path or "/api/qa/chat",
        body=body,
        headers=headers,
    )
    response = connection.getresponse()
    if response.status != 200 or "text/event-stream" not in (response.getheader("Content-Type") or ""):
        detail = response.read(2000).decode("utf-8", errors="replace")
        connection.close()
        raise RuntimeError(f"chat HTTP {response.status}: {detail}")

    events: list[str] = []
    answer_parts: list[str] = []
    final_payload: dict[str, Any] = {}
    tool_starts: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    current_event = "message"
    while True:
        raw_line = response.readline()
        if not raw_line:
            break
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip() or "message"
            events.append(current_event)
            continue
        if not line.startswith("data:"):
            continue
        data_text = line.split(":", 1)[1].strip()
        try:
            data = json.loads(data_text)
        except json.JSONDecodeError:
            data = {"raw": data_text}
        if current_event == "delta":
            answer_parts.append(str(data.get("delta") or ""))
        elif current_event == "tool_start" and isinstance(data, dict):
            tool_starts.append(data)
        elif current_event == "tool_result" and isinstance(data, dict):
            tool_results.append(data)
        elif current_event == "final" and isinstance(data, dict):
            final_payload = data
        elif current_event == "error":
            raise RuntimeError(f"SSE error: {data}")
        elif current_event == "done":
            break
    connection.close()

    snapshot = final_payload.get("cross_source_snapshot") or {}
    facts = snapshot.get("facts") or []
    by_id = {str(item.get("fact_id")): item for item in facts if isinstance(item, dict)}
    si_value = by_id.get("si_avg", {}).get("value")
    top_value = by_id.get("P_top", {}).get("value")
    independent_ratio = None
    try:
        si_number = float(si_value)
        top_number = float(top_value)
        if math.isfinite(si_number) and math.isfinite(top_number) and si_number != 0:
            independent_ratio = top_number / si_number
    except (TypeError, ValueError):
        pass

    answer = "".join(answer_parts).strip()
    answer_numbers = [float(value) for value in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?", answer)]
    ratio_mentioned = bool(
        independent_ratio is not None
        and any(abs(value - independent_ratio) <= max(0.02, abs(independent_ratio) * 0.01) for value in answer_numbers)
    )
    source_status = snapshot.get("source_status") or []
    servers = list(dict.fromkeys(
        str(item.get("server_id") or "") for item in source_status if isinstance(item, dict) and item.get("server_id")
    ))
    return {
        "schema": "ops.8093.cross-mcp-computation.v1",
        "ok": bool(final_payload.get("ok")),
        "request_count": 1,
        "question": question,
        "access_mode": bootstrap_payload.get("access_mode"),
        "events": events,
        "servers": servers,
        "cross_service": len(servers) >= 2,
        "source_status": source_status,
        "facts": facts,
        "independent_calculation": {
            "formula": "P_top / si_avg",
            "P_top": top_value,
            "si_avg": si_value,
            "result": independent_ratio,
        },
        "answer": answer,
        "answer_mentions_independent_ratio": ratio_mentioned,
        "answer_route": final_payload.get("answer_route"),
        "mcp_cross_source": final_payload.get("mcp_cross_source"),
        "tool_starts": tool_starts,
        "tool_results": tool_results,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://10.30.220.12:8093/api/qa/chat")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--inspect-last",
        action="store_true",
        help="Read the latest persisted guest messages without sending a chat request.",
    )
    parser.add_argument(
        "--question",
        default="请查询上一炉铁水Si平均值和当前顶压，并分析两者的数值比值（顶压÷Si），明确列出两个来源、原始数值和计算过程。",
    )
    args = parser.parse_args()
    if args.inspect_last:
        parsed = urlparse(args.url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        _, payload = bootstrap(base_url, min(args.timeout, 30))
        messages = payload.get("messages") or []
        result = {
            "schema": "ops.8093.cross-mcp-computation-history.v1",
            "request_count": 0,
            "access_mode": payload.get("access_mode"),
            "conversation_id": (payload.get("conversation") or {}).get("id"),
            "messages": messages[-4:],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    result = run_once(args.url, args.question, args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
