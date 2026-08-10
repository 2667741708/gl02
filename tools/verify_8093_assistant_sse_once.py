"""Run exactly one controlled 8093 assistant SSE acceptance request.

OPS-8093-ASSISTANT-HEALTH-GUARD-FIX-20260804
"""

from __future__ import annotations

import argparse
import http.client
import json
import time
from typing import Any
from urllib.parse import urlparse


APPROVED_MODEL = "chiqiong-blast-furnace:latest"


def get_json(url: str, timeout: int) -> dict[str, Any]:
    parsed = urlparse(url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    connection.request("GET", path, headers={"Accept": "application/json", "Cache-Control": "no-cache"})
    response = connection.getresponse()
    body = response.read()
    connection.close()
    if not 200 <= response.status < 300:
        raise RuntimeError(f"GET {url} returned HTTP {response.status}")
    return json.loads(body.decode("utf-8", errors="replace"))


def assert_runtime(status: dict[str, Any], processes: dict[str, Any]) -> None:
    if not status.get("ok") or not status.get("proxy_ok") or not status.get("model_ok"):
        raise RuntimeError(f"8093 model status is not healthy: {status}")
    models = processes.get("models") or []
    names = [str(item.get("name") or "") for item in models]
    if names != [APPROVED_MODEL]:
        raise RuntimeError(f"unexpected loaded models: {names}")


def run_sse(url: str, question: str, timeout: int, *, use_mcp_tools: bool | None = False) -> dict[str, Any]:
    # The default one-request smoke payload is intentionally {"use_mcp_tools": False}.
    parsed = urlparse(url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    payload = {"message": question, "stream": True}
    if use_mcp_tools is not None:
        payload["use_mcp_tools"] = use_mcp_tools
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    started = time.perf_counter()
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    connection.request(
        "POST",
        path,
        body=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream",
            "X-BF-Acceptance-ID": "OPS-8093-ASSISTANT-HEALTH-GUARD-FIX-20260804",
        },
    )
    response = connection.getresponse()
    headers_ms = round((time.perf_counter() - started) * 1000, 1)
    content_type = response.getheader("Content-Type") or ""
    if response.status != 200 or "text/event-stream" not in content_type:
        preview = response.read(1000).decode("utf-8", errors="replace")
        connection.close()
        raise RuntimeError(f"SSE HTTP {response.status} content_type={content_type!r} body={preview!r}")

    events: list[str] = []
    timeline: list[dict[str, Any]] = []
    start_stages: list[str] = []
    answer_parts: list[str] = []
    final_payload: dict[str, Any] | None = None
    error_payload: dict[str, Any] | None = None
    prepared_payload: dict[str, Any] | None = None
    tool_starts: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    conversation_id = ""
    current_event = "message"
    first_delta_ms: float | None = None
    final_ms: float | None = None
    while True:
        raw = response.readline()
        if not raw:
            break
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip() or "message"
            events.append(current_event)
            timeline.append({"event": current_event, "at_ms": elapsed_ms})
            continue
        if not line.startswith("data:"):
            continue
        data_text = line.split(":", 1)[1].strip()
        try:
            data = json.loads(data_text)
        except json.JSONDecodeError:
            data = {"raw": data_text}
        if current_event == "start":
            stage = str(data.get("stage") or "")
            if stage:
                start_stages.append(stage)
            if stage == "prepared":
                prepared_payload = data
            conversation = data.get("conversation") or {}
            conversation_id = conversation_id or str(conversation.get("id") or "")
        elif current_event == "delta":
            if first_delta_ms is None:
                first_delta_ms = elapsed_ms
            answer_parts.append(str(data.get("delta") or ""))
        elif current_event == "tool_start":
            if isinstance(data, dict):
                tool_starts.append(data)
        elif current_event == "tool_result":
            if isinstance(data, dict):
                tool_results.append(data)
        elif current_event == "final":
            final_payload = data
            final_ms = elapsed_ms
            conversation = data.get("conversation") or {}
            conversation_id = conversation_id or str(conversation.get("id") or "")
        elif current_event == "error":
            error_payload = data
        elif current_event == "done":
            break
    total_ms = round((time.perf_counter() - started) * 1000, 1)
    connection.close()

    answer = "".join(answer_parts).strip()
    required_events = {"start", "delta", "final", "done"}
    missing = sorted(required_events.difference(events))
    if error_payload:
        raise RuntimeError(f"SSE returned error: {error_payload}")
    if missing:
        raise RuntimeError(f"SSE missing events {missing}; received={events}")
    if start_stages[:2] != ["preparing", "prepared"]:
        raise RuntimeError(f"unexpected start stages: {start_stages}")
    if not answer:
        raise RuntimeError("SSE answer is empty")
    if not final_payload or not final_payload.get("ok"):
        raise RuntimeError(f"SSE final payload is not successful: {final_payload}")
    if not conversation_id:
        raise RuntimeError("SSE did not return a conversation id")

    return {
        "http_status": response.status,
        "content_type": content_type,
        "headers_ms": headers_ms,
        "first_delta_ms": first_delta_ms,
        "final_ms": final_ms,
        "total_ms": total_ms,
        "events": events,
        "start_stages": start_stages,
        "timeline": timeline,
        "conversation_id": conversation_id,
        "answer": answer,
        "answer_chars": len(answer),
        "prepared_knowledge": (prepared_payload or {}).get("knowledge"),
        "prepared_mcp_prefetch": (prepared_payload or {}).get("mcp_prefetch"),
        "prepared_mcp_tool_calling": bool((prepared_payload or {}).get("mcp_tool_calling")),
        "tool_starts": tool_starts,
        "tool_results": tool_results,
        "mcp_tool_trace": (final_payload or {}).get("mcp_tool_trace") or [],
        "qa_prepare_timing_ms": next(
            (
                item.get("qa_prepare_timing_ms")
                for item in [final_payload or {}]
                if isinstance(item.get("qa_prepare_timing_ms"), dict)
            ),
            None,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one controlled 8093 assistant SSE acceptance request.")
    parser.add_argument("--url", default="http://127.0.0.1:8093/api/qa/chat")
    parser.add_argument("--status-url", default="http://127.0.0.1:8093/api/ollama/status")
    parser.add_argument("--ps-url", default="http://127.0.0.1:11434/api/ps")
    parser.add_argument("--timeout", type=int, default=300)
    mcp_mode = parser.add_mutually_exclusive_group()
    mcp_mode.add_argument(
        "--use-mcp-tools",
        action="store_true",
        help="Force the assistant acceptance request through the configured MCP tool host.",
    )
    mcp_mode.add_argument(
        "--auto-mcp-tools",
        action="store_true",
        help="Omit the force flag and let the production intent router decide whether MCP is needed.",
    )
    parser.add_argument(
        "--require-knowledge",
        action="store_true",
        help="Require the prepared SSE event to show that knowledge retrieval ran.",
    )
    parser.add_argument(
        "--question",
        default="运维验收：请只用一句话回答‘智能助手回复链路正常’，不要查询数据库，不要调用工具。",
    )
    args = parser.parse_args()

    status_before = get_json(args.status_url, 20)
    processes_before = get_json(args.ps_url, 20)
    assert_runtime(status_before, processes_before)
    tool_mode = None if args.auto_mcp_tools else args.use_mcp_tools
    sse = run_sse(args.url, args.question, args.timeout, use_mcp_tools=tool_mode)
    if args.require_knowledge:
        knowledge = sse.get("prepared_knowledge") or {}
        intent = knowledge.get("intent") or {}
        if not knowledge.get("enabled"):
            raise RuntimeError(f"knowledge retrieval did not run: {knowledge}")
        if intent.get("skipped"):
            raise RuntimeError(f"knowledge retrieval was skipped: {intent}")
        if not intent.get("intent_type"):
            raise RuntimeError(f"knowledge intent is missing: {intent}")
    status_after = get_json(args.status_url, 20)
    processes_after = get_json(args.ps_url, 20)
    assert_runtime(status_after, processes_after)

    print(
        json.dumps(
            {
                "schema": "ops.8093.assistant-sse-once.v1",
                "requirement_id": "OPS-8093-ASSISTANT-HEALTH-GUARD-FIX-20260804",
                "ok": True,
                "request_count": 1,
                "question": args.question,
                "require_knowledge": args.require_knowledge,
                "sse": sse,
                "runtime_before": {
                    "status_ok": status_before.get("ok"),
                    "model_ok": status_before.get("model_ok"),
                    "loaded_models": [item.get("name") for item in processes_before.get("models") or []],
                },
                "runtime_after": {
                    "status_ok": status_after.get("ok"),
                    "model_ok": status_after.get("model_ok"),
                    "loaded_models": [item.get("name") for item in processes_after.get("models") or []],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
