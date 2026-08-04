"""Live multi-turn acceptance for compact colloquial MCP context inheritance.

The test talks to the normal 8093 QA endpoint. It intentionally uses
low-information follow-ups such as "画出来" and "换成两小时", then verifies
the actual MCP tool arguments instead of accepting a fluent answer alone.
"""
from __future__ import annotations

import argparse
import http.client
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen


SEQUENCES = (
    (
        "pressure_relation",
        (
            ("比较最近半小时炉顶压力和总压差", None, None, None),
            ("画出来", "plot_gl02_trends", ("P_top", "DP_total"), 30),
            ("换成两小时", "plot_gl02_trends", ("P_top", "DP_total"), 120),
            ("再加上透气性一起看", "plot_gl02_trends", ("P_top", "DP_total", "PI"), 120),
        ),
    ),
    (
        "burden_level",
        (
            ("南探尺最近一小时", None, None, None),
            ("北尺也加上", None, None, None),
            ("一张图", "plot_gl02_trends", ("L_south", "L_north"), 60),
        ),
    ),
)


def post_sse(url: str, message: str, conversation_id: str | None, timeout: int) -> dict[str, Any]:
    parsed = urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    request_payload: dict[str, Any] = {"message": message, "stream": True}
    if conversation_id:
        request_payload["conversation_id"] = conversation_id
    body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
    conn = conn_cls(parsed.hostname, parsed.port, timeout=timeout)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    started = time.perf_counter()
    current_event = ""
    final_payload: dict[str, Any] = {}
    tool_calls: list[dict[str, Any]] = []
    image_urls: list[str] = []
    answer_parts: list[str] = []
    errors: list[dict[str, Any]] = []
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json; charset=utf-8", "Accept": "text/event-stream"},
        )
        response = conn.getresponse()
        while True:
            raw = response.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
                continue
            if not line.startswith("data:"):
                continue
            try:
                payload = json.loads(line.split(":", 1)[1].strip())
            except json.JSONDecodeError:
                continue
            if current_event == "tool_start":
                tool_calls.append(
                    {
                        "tool": str(payload.get("tool") or ""),
                        "arguments": payload.get("arguments") or {},
                    }
                )
            elif current_event == "tool_result":
                result = payload.get("result") or {}
                image_url = str(result.get("image_url") or "") if isinstance(result, dict) else ""
                if image_url:
                    image_urls.append(image_url)
            elif current_event == "delta":
                answer_parts.append(str(payload.get("delta") or ""))
            elif current_event == "final":
                final_payload = payload
                for trace in payload.get("mcp_tool_trace") or []:
                    result = (trace or {}).get("result") or {}
                    image_url = str(result.get("image_url") or "") if isinstance(result, dict) else ""
                    if image_url and image_url not in image_urls:
                        image_urls.append(image_url)
            elif current_event == "error":
                errors.append(payload)
        return {
            "http_status": response.status,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "answer": str(final_payload.get("answer") or "".join(answer_parts)),
            "conversation_id": str(((final_payload.get("conversation") or {}).get("id")) or conversation_id or ""),
            "tool_calls": tool_calls,
            "image_urls": image_urls,
            "errors": errors,
        }
    finally:
        conn.close()


def image_status(base_url: str, image_url: str, timeout: int) -> dict[str, Any]:
    parsed = urlparse(base_url)
    absolute = f"{parsed.scheme}://{parsed.netloc}{image_url}"
    with urlopen(absolute, timeout=timeout) as response:
        return {
            "url": image_url,
            "status": response.status,
            "content_type": response.headers.get("Content-Type"),
        }


def matching_call(
    calls: list[dict[str, Any]],
    expected_tool: str,
    expected_variables: tuple[str, ...],
    expected_minutes: int,
) -> tuple[bool, dict[str, Any] | None]:
    expected_set = set(expected_variables)
    for call in calls:
        if call.get("tool") != expected_tool:
            continue
        arguments = call.get("arguments") or {}
        if set(arguments.get("variables") or []) != expected_set:
            continue
        start = str(arguments.get("start_time") or "")
        end = str(arguments.get("end_time") or "")
        if not start or not end:
            continue
        from datetime import datetime

        duration = round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60)
        if abs(duration - expected_minutes) <= 1:
            return True, call
    return False, None


def main() -> int:
    parser = argparse.ArgumentParser(description="8093 MCP结构化多轮口语上下文验收。")
    parser.add_argument("--url", default="http://10.30.220.12:8093/api/qa/chat")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    all_ok = True
    for sequence_id, turns in SEQUENCES:
        conversation_id = None
        for turn_index, (message, tool, variables, minutes) in enumerate(turns, start=1):
            print(f"[{sequence_id} {turn_index}/{len(turns)}] {message}", flush=True)
            result = post_sse(args.url, message, conversation_id, args.timeout)
            conversation_id = result["conversation_id"] or conversation_id
            turn_ok = result["http_status"] == 200 and bool(result["answer"].strip()) and bool(conversation_id)
            matched_call = None
            if tool and variables and minutes:
                matched, matched_call = matching_call(result["tool_calls"], tool, variables, minutes)
                turn_ok = turn_ok and matched
                if matched and result["image_urls"]:
                    result["image_checks"] = [
                        image_status(args.url, image_url, args.timeout) for image_url in result["image_urls"]
                    ]
                    turn_ok = turn_ok and all(
                        check["status"] == 200 and "image/png" in str(check["content_type"])
                        for check in result["image_checks"]
                    )
            result.update(
                {
                    "sequence_id": sequence_id,
                    "turn_index": turn_index,
                    "message": message,
                    "expected_tool": tool,
                    "expected_variables": list(variables or ()),
                    "expected_minutes": minutes,
                    "matched_call": matched_call,
                    "ok": turn_ok,
                }
            )
            all_ok = all_ok and turn_ok
            results.append(result)
            print(
                json.dumps(
                    {
                        "ok": turn_ok,
                        "elapsed_ms": result["elapsed_ms"],
                        "conversation_id": conversation_id,
                        "tool_calls": result["tool_calls"],
                        "image_urls": result["image_urls"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    report = {
        "ok": all_ok,
        "endpoint": args.url,
        "sequence_count": len(SEQUENCES),
        "turn_count": len(results),
        "passed": sum(1 for result in results if result["ok"]),
        "results": results,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
