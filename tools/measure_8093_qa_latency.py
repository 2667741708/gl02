from __future__ import annotations

import argparse
import http.client
import json
import time
from dataclasses import dataclass, asdict
from urllib.parse import urlparse


@dataclass
class Timing:
    name: str
    ok: bool
    status: int | None = None
    headers_ms: float | None = None
    first_event_ms: float | None = None
    first_delta_ms: float | None = None
    final_ms: float | None = None
    total_ms: float | None = None
    events: list[str] | None = None
    event_timeline_ms: list[dict] | None = None
    prepared_timing_ms: dict | None = None
    error: str = ""
    preview: str = ""


def post_raw(url: str, payload: dict, accept: str = "application/json", timeout: int = 300) -> tuple[int, float, bytes]:
    parsed = urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start = time.perf_counter()
    conn = conn_cls(parsed.hostname, parsed.port, timeout=timeout)
    conn.request(
        "POST",
        path,
        body=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": accept,
        },
    )
    resp = conn.getresponse()
    headers_ms = (time.perf_counter() - start) * 1000
    data = resp.read()
    total_ms = (time.perf_counter() - start) * 1000
    conn.close()
    return resp.status, headers_ms, data, total_ms


def post_json_timing(name: str, url: str, payload: dict, timeout: int) -> Timing:
    try:
        status, headers_ms, data, total_ms = post_raw(url, payload, timeout=timeout)
        text = data.decode("utf-8", errors="replace")
        ok = 200 <= status < 300
        return Timing(
            name=name,
            ok=ok,
            status=status,
            headers_ms=round(headers_ms, 1),
            total_ms=round(total_ms, 1),
            preview=text[:500],
        )
    except Exception as exc:  # noqa: BLE001
        return Timing(name=name, ok=False, error=f"{type(exc).__name__}: {exc}")


def post_ollama_stream_timing(name: str, url: str, payload: dict, timeout: int) -> Timing:
    parsed = urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start = time.perf_counter()
    try:
        conn = conn_cls(parsed.hostname, parsed.port, timeout=timeout)
        conn.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json; charset=utf-8", "Accept": "application/x-ndjson"},
        )
        resp = conn.getresponse()
        headers_ms = (time.perf_counter() - start) * 1000
        first_line_ms = None
        first_delta_ms = None
        preview_parts: list[str] = []
        while True:
            line = resp.readline()
            if not line:
                break
            now_ms = (time.perf_counter() - start) * 1000
            if first_line_ms is None:
                first_line_ms = now_ms
            try:
                obj = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            content = ((obj.get("message") or {}).get("content") or obj.get("response") or "")
            if content:
                preview_parts.append(content)
                if first_delta_ms is None:
                    first_delta_ms = now_ms
            if obj.get("done"):
                break
        total_ms = (time.perf_counter() - start) * 1000
        conn.close()
        return Timing(
            name=name,
            ok=200 <= resp.status < 300,
            status=resp.status,
            headers_ms=round(headers_ms, 1),
            first_event_ms=round(first_line_ms, 1) if first_line_ms is not None else None,
            first_delta_ms=round(first_delta_ms, 1) if first_delta_ms is not None else None,
            total_ms=round(total_ms, 1),
            preview="".join(preview_parts)[:500],
        )
    except Exception as exc:  # noqa: BLE001
        return Timing(name=name, ok=False, error=f"{type(exc).__name__}: {exc}")


def post_sse_timing(name: str, url: str, payload: dict, timeout: int) -> Timing:
    parsed = urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start = time.perf_counter()
    events: list[str] = []
    event_timeline_ms: list[dict] = []
    prepared_timing_ms = None
    preview_parts: list[str] = []
    first_event_ms = None
    first_delta_ms = None
    final_ms = None
    current_event = None
    try:
        conn = conn_cls(parsed.hostname, parsed.port, timeout=timeout)
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "text/event-stream",
            },
        )
        resp = conn.getresponse()
        headers_ms = (time.perf_counter() - start) * 1000
        while True:
            line_raw = resp.readline()
            if not line_raw:
                break
            now_ms = (time.perf_counter() - start) * 1000
            line = line_raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
                events.append(current_event)
                if len(event_timeline_ms) < 40:
                    event_timeline_ms.append({"event": current_event, "at_ms": round(now_ms, 1)})
                if first_event_ms is None:
                    first_event_ms = now_ms
            elif line.startswith("data:"):
                data_text = line.split(":", 1)[1].strip()
                if current_event == "start":
                    try:
                        start_payload = json.loads(data_text)
                        if isinstance(start_payload.get("qa_prepare_timing_ms"), dict):
                            prepared_timing_ms = start_payload["qa_prepare_timing_ms"]
                    except json.JSONDecodeError:
                        pass
                if current_event == "delta":
                    if first_delta_ms is None:
                        first_delta_ms = now_ms
                    try:
                        obj = json.loads(data_text)
                        preview_parts.append(str(obj.get("delta") or obj.get("content") or ""))
                    except json.JSONDecodeError:
                        preview_parts.append(data_text)
                if current_event in {"final", "done"} and final_ms is None:
                    final_ms = now_ms
            if current_event == "done":
                break
        total_ms = (time.perf_counter() - start) * 1000
        conn.close()
        return Timing(
            name=name,
            ok=200 <= resp.status < 300,
            status=resp.status,
            headers_ms=round(headers_ms, 1),
            first_event_ms=round(first_event_ms, 1) if first_event_ms is not None else None,
            first_delta_ms=round(first_delta_ms, 1) if first_delta_ms is not None else None,
            final_ms=round(final_ms, 1) if final_ms is not None else None,
            total_ms=round(total_ms, 1),
            events=events[:20],
            event_timeline_ms=event_timeline_ms,
            prepared_timing_ms=prepared_timing_ms,
            preview="".join(preview_parts)[:500],
        )
    except Exception as exc:  # noqa: BLE001
        return Timing(name=name, ok=False, error=f"{type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure 8093 QA and direct Ollama latency.")
    parser.add_argument("--qa-url", default="http://10.30.220.12:8093/api/qa/chat")
    parser.add_argument("--ollama-url", default="http://10.30.220.12:11434/api/chat")
    parser.add_argument("--model", default="chiqiong-blast-furnace:latest")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--question", default="请用一句话回答：当前模型服务是否在线？")
    parser.add_argument("--data-question", default="请查询T_top当前最新值，并说明数据时间。")
    parser.add_argument("--knowledge-question", default="高炉压差持续升高通常说明什么，应重点观察哪些指标？")
    parser.add_argument("--knowledge-only", action="store_true")
    parser.add_argument("--simple-only", action="store_true")
    parser.add_argument("--data-only", action="store_true")
    args = parser.parse_args()

    snapshot = {
        "source": "latency_probe",
        "diagnosis": {"main_label": "normal", "label": "normal"},
    }
    qa_payload = {
        "message": args.question,
        "stream": False,
        "current_snapshot": snapshot,
        "use_mcp_tools": False,
    }
    qa_stream_payload = dict(qa_payload, stream=True)
    data_stream_payload = {
        "message": args.data_question,
        "stream": True,
        "current_snapshot": snapshot,
    }
    data_prefetch_only_payload = dict(data_stream_payload, use_mcp_tools=False)
    knowledge_stream_payload = {
        "message": args.knowledge_question,
        "stream": True,
        "current_snapshot": snapshot,
        "use_mcp_tools": False,
    }
    ollama_payload = {
        "model": args.model,
        "stream": True,
        "messages": [{"role": "user", "content": args.question}],
        "think": False,
        "options": {"temperature": 0.1, "num_predict": 120, "think": False},
    }

    if args.simple_only:
        results = [post_sse_timing("qa_8093_sse_simple_no_tools", args.qa_url, qa_stream_payload, args.timeout)]
    elif args.data_only:
        results = [post_sse_timing("qa_8093_sse_data_default", args.qa_url, data_stream_payload, args.timeout)]
    elif args.knowledge_only:
        results = [post_sse_timing("qa_8093_sse_knowledge", args.qa_url, knowledge_stream_payload, args.timeout)]
    else:
        results = [
            post_ollama_stream_timing("direct_ollama_stream_simple", args.ollama_url, ollama_payload, args.timeout),
            post_json_timing("qa_8093_json_simple_no_tools", args.qa_url, qa_payload, args.timeout),
            post_sse_timing("qa_8093_sse_simple_no_tools", args.qa_url, qa_stream_payload, args.timeout),
            post_sse_timing("qa_8093_sse_data_default", args.qa_url, data_stream_payload, args.timeout),
            post_sse_timing(
                "qa_8093_sse_data_prefetch_only",
                args.qa_url,
                data_prefetch_only_payload,
                args.timeout,
            ),
            post_sse_timing("qa_8093_sse_knowledge", args.qa_url, knowledge_stream_payload, args.timeout),
        ]
    print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
