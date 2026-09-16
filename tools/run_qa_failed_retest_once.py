"""Retest reviewed QA failures against production once, with durable no-replay claims."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
from pathlib import Path
import time
import sys
from urllib.parse import urlparse
from urllib.request import urlopen


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def model_required(question: str) -> bool:
    backend = Path(__file__).resolve().parents[1] / "高炉前端数据/智能助手/backend"
    sys.path.insert(0, str(backend))
    import qa_task_plan
    plan = qa_task_plan.build_task_plan(question)
    if "document_knowledge" in plan.get("intents", []) and len(plan["intents"]) > 1:
        import qa_document_compound
        remaining = [part for part in qa_document_compound.clauses(question)
                     if "document_knowledge" not in qa_task_plan.build_task_plan(part)["intents"]]
        if remaining:
            prepared = {"hidden_context": {"qa_task_plan": plan},
                        "document_compound": {"remainder_question": "；".join(remaining)}}
            child = qa_document_compound.prefetch_plan(prepared)
            if child.get("intents") == ["live_data"]:
                return False
    return not (plan.get("intents") == ["document_knowledge"] and not plan.get("allow_mcp_tools") and not plan.get("allow_prefetch"))


def status_ready(url: str, timeout: int, evidence: list | None = None, need_model: bool = True) -> bool:
    # Only GET readiness is retried, before creating the durable POST claim.
    # Never retry a question or infer request completion from readiness.
    for attempt in range(3):
        try:
            with urlopen(url, timeout=timeout) as response:
                status = json.load(response)
            observed = {key: status.get(key) is True for key in ("ok", "proxy_ok", "ollama_ok", "model_ok")}
        except Exception as exc:
            observed = {"error_type": type(exc).__name__}
        if evidence is not None:
            evidence.append({"attempt": attempt + 1, **observed})
        required = ("ok", "proxy_ok", "ollama_ok", "model_ok") if need_model else ("proxy_ok",)
        if all(observed.get(key) for key in required):
            return True
        if attempt < 2:
            time.sleep(0.25)
    return False


def request_once(url: str, question: str, timeout: int, case_id: str) -> dict:
    parsed = urlparse(url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    body = json.dumps({"message": question, "stream": True, "response_projection": "turn"}, ensure_ascii=False).encode("utf-8")
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    started = time.perf_counter()
    connection.request(
        "POST",
        path,
        body=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream",
            "Origin": f"{parsed.scheme}://{parsed.netloc}",
            "X-BF-Acceptance-ID": f"REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916:{case_id}",
        },
    )
    response = connection.getresponse()
    result = {
        "http_status": response.status,
        "content_type": response.getheader("Content-Type") or "",
        "events": [],
        "start_stages": [],
        "answer": "",
        "prepared": None,
        "final": None,
        "error": None,
        "tool_starts": [],
        "tool_results": [],
        "terminated": False,
        "determinate": False,
    }
    if response.status != 200 or "text/event-stream" not in result["content_type"]:
        result["response_preview"] = response.read(2000).decode("utf-8", errors="replace")
        result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        result["determinate"] = True
        connection.close()
        return result
    current_event = "message"
    answer_parts = []
    while True:
        raw = response.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip() or "message"
            result["events"].append(current_event)
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
                result["start_stages"].append(stage)
            if stage == "prepared":
                result["prepared"] = data
        elif current_event == "delta":
            answer_parts.append(str(data.get("delta") or ""))
        elif current_event == "tool_start":
            result["tool_starts"].append(data)
        elif current_event == "tool_result":
            result["tool_results"].append(data)
        elif current_event == "final":
            result["final"] = data
        elif current_event == "error":
            result["error"] = data
            result["determinate"] = True
        elif current_event == "done":
            result["terminated"] = True
            result["determinate"] = True
            break
    result["answer"] = "".join(answer_parts).strip()
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    connection.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://10.30.220.12:8093/api/qa/chat")
    parser.add_argument("--status-url", default="http://10.30.220.12:8093/api/ollama/status")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--skip-case", action="append", default=[])
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    source = load(args.failures)
    skipped = set(args.skip_case)
    cases = [case for case in source["reviews"] if case["case_id"] not in skipped]
    if len(cases) != len({case["case_id"] for case in cases}):
        raise RuntimeError("duplicate case IDs")
    for case in cases:
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise RuntimeError("invalid case question before request")
        # Metadata must never prevent persistence after a production POST.
        case.setdefault("expected", "manual semantic review required")
        case.setdefault("failure", "reviewed regression case")
    args.output.mkdir(parents=True, exist_ok=False)
    progress_path = args.output / "progress.json"
    progress = {
        "schema": "bf.qa.failed-retest-progress.v1",
        "requirement_id": "REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916",
        "source_sha256": hashlib.sha256(args.failures.read_bytes()).hexdigest(),
        "total": len(cases),
        "completed": 0,
        "requests": 0,
        "automatic_retries": 0,
        "state": "running",
        "results": [],
        "started_at": time.time(),
    }
    write(progress_path, progress)
    try:
        for case in cases:
            case_id = case["case_id"]
            progress["active_case"] = case_id
            write(progress_path, progress)
            readiness = []
            need_model = model_required(case["question"])
            progress["model_required"] = need_model
            ready = status_ready(args.status_url, 6, readiness, need_model)
            progress["readiness_checks"] = readiness
            write(progress_path, progress)
            if not ready:
                raise RuntimeError("model unavailable before request; no request sent")
            claim_path = args.output / f"{case_id}.claim"
            with claim_path.open("x", encoding="utf-8") as claim:
                json.dump(
                    {
                        "case_id": case_id,
                        "prompt_sha256": hashlib.sha256(case["question"].encode("utf-8")).hexdigest(),
                        "request_may_be_sent": True,
                        "created_at": time.time(),
                    },
                    claim,
                )
            progress["requests"] += 1
            write(progress_path, progress)
            result = request_once(args.url, case["question"], args.timeout, case_id)
            private = {
                "case_id": case_id,
                "question": case["question"],
                "expected": case.get("expected"),
                "previous_failure": case.get("failure"),
                "request_count": 1,
                **result,
            }
            write(args.output / f"{case_id}.json", private)
            final = result.get("final") or {}
            progress["results"].append(
                {
                    "case_id": case_id,
                    "http_status": result.get("http_status"),
                    "terminated": result.get("terminated"),
                    "determinate": result.get("determinate"),
                    "has_answer": bool(result.get("answer")),
                    "answer_chars": len(result.get("answer") or ""),
                    "error_code": (result.get("error") or {}).get("code"),
                    "route": final.get("answer_route"),
                    "tool_calls": len(result.get("tool_starts") or []),
                    "seconds": result.get("elapsed_seconds"),
                    "answer_contract": "pending_review" if result.get("answer") else "failed",
                }
            )
            progress["completed"] += 1
            write(progress_path, progress)
            if not result.get("determinate"):
                raise RuntimeError(f"uncertain request; do not replay: {case_id}")
        progress["state"] = "completed"
        progress["active_case"] = None
    except Exception as exc:
        progress["state"] = "blocked"
        progress["error_type"] = type(exc).__name__
        progress["reason"] = str(exc)
    finally:
        progress["updated_at"] = time.time()
        write(progress_path, progress)
    print(
        json.dumps(
            {key: value for key, value in progress.items() if key != "results"},
            ensure_ascii=False,
        )
    )
    return 0 if progress["state"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
