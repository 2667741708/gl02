"""Send exactly one guest-shared SSE request that must use the read-only MCP host."""

from __future__ import annotations

import argparse
import http.client
import json
import time
from typing import Any
from urllib.parse import urlparse


QUESTION = (
    "生产验收：请调用只读传感器工具查询当前综合顶压 P_top，"
    "并返回数值、单位、数据时间、质量和来源；如果工具失败请明确说明，不要猜测。"
)


def connection_for(parsed: Any, timeout: int) -> http.client.HTTPConnection:
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    return connection_type(parsed.hostname, parsed.port, timeout=timeout)


def bootstrap(base_url: str, timeout: int) -> tuple[dict[str, Any], str]:
    parsed = urlparse(base_url)
    connection = connection_for(parsed, timeout)
    connection.request("GET", "/api/qa/bootstrap", headers={"Accept": "application/json"})
    response = connection.getresponse()
    body = response.read()
    cookies = [value.split(";", 1)[0] for name, value in response.getheaders() if name.lower() == "set-cookie"]
    connection.close()
    if response.status != 200:
        raise RuntimeError(f"bootstrap HTTP {response.status}")
    payload = json.loads(body.decode("utf-8", errors="replace"))
    if payload.get("access_mode") != "guest_shared":
        raise RuntimeError(f"unexpected access mode: {payload.get('access_mode')}")
    return payload, "; ".join(cookies)


def run_once(
    base_url: str,
    question: str,
    timeout: int,
    cookie: str,
    conversation_id: str,
    counters: dict[str, int],
    require_tool_events: bool = True,
    required_answer_terms: tuple[str, ...] = (),
    require_answer_evidence_markers: bool = True,
) -> dict[str, Any]:
    parsed = urlparse(base_url)
    connection = connection_for(parsed, timeout)
    body = json.dumps(
        {
            "conversation_id": conversation_id,
            "message": question,
            "stream": True,
            "use_mcp_tools": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "text/event-stream",
        "Origin": f"{parsed.scheme}://{parsed.netloc}",
        "X-BF-Controlled-Client": "1",
        "X-BF-Acceptance-ID": "REQ-MCP-AGENT-GOLDEN-SUITE-20260814",
    }
    if cookie:
        headers["Cookie"] = cookie
    started = time.perf_counter()
    counters["request_count"] = 1
    connection.request("POST", "/api/qa/chat", body=body, headers=headers)
    response = connection.getresponse()
    content_type = response.getheader("Content-Type") or ""
    if response.status != 200 or "text/event-stream" not in content_type:
        preview = response.read(1000).decode("utf-8", errors="replace")
        connection.close()
        raise RuntimeError(f"SSE HTTP {response.status}: {preview}")

    events: list[str] = []
    start_stages: list[str] = []
    answer_parts: list[str] = []
    tool_starts: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    public_traces: list[dict[str, Any]] = []
    analysis_starts: list[dict[str, Any]] = []
    analysis_results: list[dict[str, Any]] = []
    final_payload: dict[str, Any] | None = None
    error_payload: dict[str, Any] | None = None
    prepared_payload: dict[str, Any] | None = None
    current_event = "message"
    while True:
        raw = response.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip() or "message"
            events.append(current_event)
            continue
        if not line.startswith("data:"):
            continue
        text = line.split(":", 1)[1].strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"raw": text}
        if current_event == "start":
            stage = str(data.get("stage") or "")
            if stage:
                start_stages.append(stage)
            if stage == "prepared":
                prepared_payload = data
        elif current_event == "tool_start" and isinstance(data, dict):
            tool_starts.append(data)
        elif current_event == "tool_result" and isinstance(data, dict):
            tool_results.append(data)
        elif current_event == "trace" and isinstance(data, dict):
            public_traces.append(data)
        elif current_event == "analysis_start" and isinstance(data, dict):
            analysis_starts.append(data)
        elif current_event == "analysis_result" and isinstance(data, dict):
            analysis_results.append(data)
        elif current_event == "delta":
            answer_parts.append(str(data.get("delta") or ""))
        elif current_event == "final" and isinstance(data, dict):
            final_payload = data
        elif current_event == "error" and isinstance(data, dict):
            error_payload = data
        elif current_event == "done":
            break
    connection.close()

    answer = "".join(answer_parts).strip()
    if error_payload:
        raise RuntimeError(f"SSE error: {error_payload}")
    required_events = ["start", "delta", "final", "done"]
    if require_tool_events:
        required_events.extend(("tool_start", "tool_result"))
    for required in required_events:
        if required not in events:
            raise RuntimeError(f"missing SSE event {required}: {events}")
    if start_stages[:2] != ["preparing", "prepared"]:
        raise RuntimeError(f"unexpected start stages: {start_stages}")
    if not prepared_payload or not prepared_payload.get("mcp_tool_calling"):
        raise RuntimeError("prepared event did not enable MCP tool calling")
    if not final_payload or not final_payload.get("ok"):
        raise RuntimeError("final SSE payload is not successful")
    if not answer:
        raise RuntimeError("assistant answer is empty")
    if required_answer_terms:
        folded = answer.casefold()
        missing_terms = [term for term in required_answer_terms if term.casefold() not in folded]
        if missing_terms:
            diagnostic = {
                "missing_terms": missing_terms,
                "answer_preview": answer[:3000],
                "tool_starts": tool_starts,
                "tool_results": tool_results,
                "final_trace": (final_payload or {}).get("mcp_tool_trace") or [],
            }
            raise RuntimeError(
                "assistant answer lacks required terms: "
                + json.dumps(diagnostic, ensure_ascii=False, default=str)
            )
    elif require_answer_evidence_markers and not any(
        marker in answer for marker in ("kPa", "单位", "数据时间", "来源")
    ):
        raise RuntimeError("assistant answer lacks the required evidence fields")

    prepared_conversation = prepared_payload.get("conversation") if prepared_payload else None
    prepared_conversation_id = str(
        (prepared_payload or {}).get("conversation_id")
        or (prepared_conversation or {}).get("id")
        or ""
    ).strip()

    return {
        "events": events,
        "start_stages": start_stages,
        "tool_start_count": len(tool_starts),
        "tool_result_count": len(tool_results),
        "tool_starts": tool_starts,
        "tool_results": tool_results,
        "trace_count": len(public_traces),
        "public_traces": public_traces,
        "analysis_start_count": len(analysis_starts),
        "analysis_result_count": len(analysis_results),
        "analysis_starts": analysis_starts,
        "analysis_results": analysis_results,
        "mcp_tool_trace": final_payload.get("mcp_tool_trace") or [],
        "answer": answer,
        "answer_chars": len(answer),
        "prepared_conversation_id": prepared_conversation_id,
        "model_request_count": (
            int(final_payload["model_request_count"])
            if isinstance(final_payload.get("model_request_count"), int)
            else None
        ),
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8093")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--question", default=QUESTION)
    parser.add_argument("--allow-no-tools", action="store_true")
    parser.add_argument("--required-answer-term", action="append", default=[])
    parser.add_argument("--submitted-conversation-id")
    parser.add_argument("--require-bootstrap-conversation-rebind", action="store_true")
    parser.add_argument("--skip-answer-evidence-markers", action="store_true")
    args = parser.parse_args()

    counters = {"request_count": 0}
    try:
        boot, cookie = bootstrap(args.base_url, 30)
        conversation = boot.get("conversation")
        conversation_id = str(conversation.get("id") if isinstance(conversation, dict) else "").strip()
        if not conversation_id:
            raise RuntimeError("bootstrap conversation.id is missing")
        submitted_conversation_id = str(args.submitted_conversation_id or conversation_id).strip()
        result = run_once(
            args.base_url,
            args.question,
            args.timeout,
            cookie,
            submitted_conversation_id,
            counters,
            require_tool_events=not args.allow_no_tools,
            required_answer_terms=tuple(args.required_answer_term),
            require_answer_evidence_markers=not args.skip_answer_evidence_markers,
        )
        if args.require_bootstrap_conversation_rebind:
            if submitted_conversation_id == conversation_id:
                raise RuntimeError("rebind verification requires a non-bootstrap submitted conversation ID")
            if result.get("prepared_conversation_id") != conversation_id:
                raise RuntimeError(
                    "prepared conversation did not rebind to bootstrap shared room: "
                    f"{result.get('prepared_conversation_id')} != {conversation_id}"
                )
        payload = {
            "schema": "bf.8093-mcp-gold-sse-once.v1",
            "requirement_id": "REQ-MCP-AGENT-GOLDEN-SUITE-20260814",
            "ok": True,
            "request_count": counters["request_count"],
            "model_request_count": result["model_request_count"],
            "access_mode": boot.get("access_mode"),
            "conversation_id": conversation_id,
            "submitted_conversation_id": submitted_conversation_id,
            "question": args.question,
            "sse": result,
        }
        exit_code = 0
    except Exception as exc:  # noqa: BLE001 - emit one structured acceptance record
        payload = {
            "schema": "bf.8093-mcp-gold-sse-once.v1",
            "requirement_id": "REQ-MCP-AGENT-GOLDEN-SUITE-20260814",
            "ok": False,
            "request_count": counters["request_count"],
            "model_request_count": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
