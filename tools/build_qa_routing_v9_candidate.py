"""Build scoped subsection and mixed-request repair from accepted V8 bytes."""
from __future__ import annotations
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

BASELINE_SHA = "7f8b79fbfa98db94f55d2c7c40f0a0749c953ba50a46448933929f2ee1ff7841"

def replace(source, old, new, expected=1):
    if source.count(old) != expected:
        raise ValueError(f"Accepted seam changed: {old[:80]}")
    return source.replace(old, new)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v8-candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = args.v8_candidate.resolve()
    root = Path(__file__).resolve().parents[1]
    raw = (baseline / "ollama_proxy_server.py").read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASELINE_SHA:
        raise ValueError("Accepted V8 proxy hash mismatch")
    before = raw.decode("utf-8")
    source = replace(before, "if qa_evidence_policy.code_requested(user_text):\n        return QA_ANSWER_ROUTE_CODE", "if qa_evidence_policy.code_request_only(user_text):\n        return QA_ANSWER_ROUTE_CODE")
    for indent in (16, 20):
        pad = " " * indent
        source = replace(source, "\n" + pad + "answer = qa_evidence_policy.enforce_no_code(answer)\n", "\n" + pad + "answer = qa_evidence_policy.apply_request_boundary(question, answer)\n" + pad + "tool_result = qa_evidence_policy.boundary_result(question, tool_result)\n")
    start = source.index('            last_safe_stream_content = ""\n')
    end = source.index('            with db_connect() as conn:\n', start)
    source = source[:start] + '''            stream_completed = False
            with urlopen(req, timeout=300) as resp:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    try:
                        obj = json.loads(line.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        continue
                    content = ((obj.get("message") or {}).get("content") or obj.get("response") or "")
                    if content:
                        answer_parts.append(content)
                    if obj.get("done"):
                        merge_ollama_response_timing(model_timing, ollama_response_timing(obj))
                        stream_completed = obj.get("done_reason") != "length"
                        break
            answer = qa_evidence_policy.apply_request_boundary(question, clean_llm_output("".join(answer_parts)))
            answer = append_mcp_chart_links(answer, mcp_tool_trace)
            tool_result = dict(tool_result)
            tool_result["completion"] = {
                "terminal_state": "answered_pending_review" if stream_completed and answer.strip() else "partial",
                "complete": False,
                "stream_completed": stream_completed,
                "semantic_review_required": True,
            }
            tool_result = qa_evidence_policy.boundary_result(question, tool_result)
            mark_first_visible_token_timing(model_timing, request_started)
            if not self.write_qa_event("delta", {"delta": answer, "content": answer}):
                raise ConnectionAbortedError("SSE client disconnected")
''' + source[end:]
    ast.parse(source)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for path in baseline.glob("*.py"):
        shutil.copyfile(path, output / path.name)
    for name in ("qa_document_knowledge.py", "qa_evidence_policy.py"):
        shutil.copyfile(root / "高炉前端数据/智能助手/backend" / name, output / name)
    (output / "ollama_proxy_server.py").write_text(source, encoding="utf-8", newline="\n")
    (output / "proxy.patch").write_text("".join(difflib.unified_diff(before.splitlines(True), source.splitlines(True), fromfile="accepted-v8", tofile="routing-v9")), encoding="utf-8", newline="\n")
    result = {"ok": True, "schema": "bf.qa.routing-v9-build.v1", "baseline_commit": "379aefb120c84e12302e180503deebfacc9d88e5", "hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob("*.py"))}}
    (output / "build.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "hashes": {k: v for k, v in result["hashes"].items() if k in {"ollama_proxy_server.py", "qa_document_knowledge.py", "qa_evidence_policy.py"}}}))

if __name__ == "__main__":
    main()
