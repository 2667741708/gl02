"""One real 8093 MES MCP acceptance request after a guarded deployment."""

from __future__ import annotations

import argparse
import http.client
import json
import time
from typing import Any
from urllib.parse import urlparse


def get_json(url: str, timeout: int = 20) -> dict[str, Any]:
    parsed = urlparse(url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    connection.request("GET", path, headers={"Accept": "application/json", "Cache-Control": "no-cache"})
    response = connection.getresponse()
    payload = response.read()
    connection.close()
    if response.status < 200 or response.status >= 300:
        raise RuntimeError(f"GET {url} returned HTTP {response.status}")
    return json.loads(payload.decode("utf-8", errors="replace"))


def status_url_for_chat(chat_url: str) -> str:
    """Return the Ollama status URL on the same host as the requested chat API."""

    parsed = urlparse(chat_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid chat URL: {chat_url}")
    return f"{parsed.scheme}://{parsed.netloc}/api/ollama/status"


def run_once(url: str, question: str, timeout: int) -> dict[str, Any]:
    parsed = urlparse(url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    body = json.dumps({"message": question, "stream": True, "use_mcp_tools": True}, ensure_ascii=False).encode("utf-8")
    started = time.perf_counter()
    connection.request(
        "POST",
        path,
        body=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream",
            "X-BF-Acceptance-ID": "OPS-8093-MULTI-MCP-HOST-20260805",
        },
    )
    response = connection.getresponse()
    if response.status != 200 or "text/event-stream" not in (response.getheader("Content-Type") or ""):
        detail = response.read(2000).decode("utf-8", errors="replace")
        connection.close()
        raise RuntimeError(f"MCP SSE HTTP/content failure: {response.status}, {detail}")

    events: list[str] = []
    start_stages: list[str] = []
    answer_parts: list[str] = []
    tool_trace: list[dict[str, Any]] = []
    final_payload: dict[str, Any] | None = None
    error_payload: dict[str, Any] | None = None
    current_event = "message"
    while True:
        line = response.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if text.startswith("event:"):
            current_event = text.split(":", 1)[1].strip() or "message"
            events.append(current_event)
            continue
        if not text.startswith("data:"):
            continue
        raw = text.split(":", 1)[1].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"raw": raw}
        if current_event == "start":
            stage = str(data.get("stage") or "")
            if stage:
                start_stages.append(stage)
        elif current_event == "tool_result":
            if isinstance(data, dict):
                tool_trace.append(data)
        elif current_event == "delta":
            answer_parts.append(str(data.get("delta") or ""))
        elif current_event == "final":
            final_payload = data if isinstance(data, dict) else None
        elif current_event == "error":
            error_payload = data if isinstance(data, dict) else {"raw": data}
        elif current_event == "done":
            break
    connection.close()
    answer = "".join(answer_parts).strip()
    if error_payload:
        raise RuntimeError(f"MCP SSE returned error: {error_payload}")
    required = {"start", "tool_start", "tool_result", "delta", "final", "done"}
    missing = sorted(required.difference(events))
    if missing:
        raise RuntimeError(f"MCP SSE missing events {missing}; received={events}")
    if start_stages[:2] != ["preparing", "prepared"]:
        raise RuntimeError(f"unexpected preparation stages: {start_stages}")
    if not answer or not final_payload or not final_payload.get("ok"):
        raise RuntimeError("MES MCP answer is empty or final payload is not successful")
    final_trace = final_payload.get("mcp_tool_trace") or []
    all_trace = [*tool_trace, *(final_trace if isinstance(final_trace, list) else [])]
    names = [str(item.get("tool") or "") for item in all_trace if isinstance(item, dict)]
    if "imes__get_current_previous_heat_si_summary" not in names:
        raise RuntimeError(f"MES composite tool was not observed: {names}")
    return {
        "ok": True,
        "request_count": 1,
        "question": question,
        "http_status": response.status,
        "events": events,
        "start_stages": start_stages,
        "tools": names,
        "answer": answer,
        "answer_chars": len(answer),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "mcp_tool_trace": final_trace,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="8093真实MES MCP单次SSE验收")
    parser.add_argument("--url", default="http://127.0.0.1:8093/api/qa/chat")
    parser.add_argument("--question", default="当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    status_url = status_url_for_chat(args.url)
    status_before = get_json(status_url)
    sse = run_once(args.url, args.question, args.timeout)
    status_after = get_json(status_url)
    result = {
        "schema": "ops.8093.multi-mcp.mes-sse-once.v1",
        "requirement_id": "OPS-8093-MULTI-MCP-HOST-20260805",
        "ok": True,
        "runtime_before_ok": bool(status_before.get("ok")),
        "runtime_after_ok": bool(status_after.get("ok")),
        "sse": sse,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
