"""Build document/prompt repair from exact accepted V7 runtime bytes."""
from __future__ import annotations
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

PROXY_SHA = "3ca45c017b4285fa04b97969801e40ec7ea6c6d333dff3136f7a794baaf315c4"


def replace(source, old, new, label):
    if source.count(old) != 1:
        raise ValueError(f"{label}: accepted seam not unique")
    return source.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v7-candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    baseline, output = args.v7_candidate.resolve(), args.output.resolve()
    if hashlib.sha256((baseline / "ollama_proxy_server.py").read_bytes()).hexdigest() != PROXY_SHA:
        raise ValueError("Accepted V7 proxy hash mismatch")
    before = (baseline / "ollama_proxy_server.py").read_text(encoding="utf-8")
    source = replace(before, "import qa_completion\n", "import qa_completion\nimport qa_document_knowledge\nimport qa_prompt_sources\n", "document provider imports")
    start = source.index('    if analysis_mode != "initial_context_explanation" and (qa_evidence_policy.code_requested(question) or qa_evidence_policy.no_live_lookup(question)):', source.index("def build_hidden_qa_messages("))
    end = source.index("    recent_history = [", start)
    source = source[:start] + '''    source_messages = qa_prompt_sources.build_source_messages(question, history, knowledge_context, analysis_mode)
    if source_messages is not None:
        return source_messages
''' + source[end:]
    source = replace(source, '    if analysis_mode == "initial_context_explanation" and assistant_rule_context:\n', '''    if analysis_mode != "initial_context_explanation":
        system_prompt += "\\n\\n" + qa_evidence_policy.PROMPT
    if analysis_mode == "initial_context_explanation" and assistant_rule_context:
''', "legacy prompt policy overlay")
    old = '''            knowledge_pack = qa_search_knowledge(
                question,
                mcp_prefetch=mcp_prefetch,
                connection=conn,
                task_plan=task_plan,
            )
'''
    new = '''            document_result = None
            if str(payload.get("analysis_mode") or "") != "initial_context_explanation":
                try:
                    document_result = qa_document_knowledge.execute_document_question(conn, question, task_plan)
                except Exception as exc:
                    if task_plan.get("intents") == ["document_knowledge"]:
                        document_result = qa_document_knowledge._outcome("文档只读查询暂不可用，未使用聊天、报表或通用知识补写正式条款。", "dependency_blocked", "document_query_unavailable")
                        emit_host_log("qa.document.failed", error_type=type(exc).__name__)
                    else:
                        raise
            knowledge_pack = ({"enabled": False, "evidence": [], "message": "本轮由核验原文执行器回答"} if document_result is not None else qa_search_knowledge(
                question,
                mcp_prefetch=mcp_prefetch,
                connection=conn,
                task_plan=task_plan,
            ))
'''
    source = replace(source, old, new, "read-only document preparation")
    source = replace(source, '                "use_mcp_tools": use_mcp_tools,\n', '                "document_result": document_result,\n                "use_mcp_tools": use_mcp_tools,\n', "prepared outcome")
    for spaces in (12, 8):
        p = " " * spaces
        seam = '\n' + p + 'if tool_result.get("answer") is None and prepared.get("history_result") is not None:\n'
        source = replace(source, seam, '\n' + p + 'if tool_result.get("answer") is None and prepared.get("document_result") is not None:\n' + p + '    tool_result = prepared["document_result"]' + seam, f"document outcome parity {spaces}")
    marker = '"completion": qa_completion.public_completion(tool_result),'
    if source.count(marker) != 3:
        raise ValueError("Expected three final completion seams")
    source = source.replace(marker, marker + '\n                        "knowledge_manifest": tool_result.get("knowledge_manifest") or [],')
    ast.parse(source)
    output.mkdir(parents=True, exist_ok=True)
    for path in baseline.glob("*.py"):
        shutil.copyfile(path, output / path.name)
    for name in ("qa_task_plan.py", "qa_document_knowledge.py", "qa_prompt_sources.py"):
        shutil.copyfile(root / "高炉前端数据/智能助手/backend" / name, output / name)
    (output / "ollama_proxy_server.py").write_text(source, encoding="utf-8", newline="\n")
    (output / "proxy.patch").write_text("".join(difflib.unified_diff(before.splitlines(True), source.splitlines(True), fromfile="accepted-v7", tofile="routing-v8")), encoding="utf-8", newline="\n")
    result = {"ok": True, "schema": "bf.qa.routing-v8-build.v1", "baseline_commit": "f46841edd06502c53fa85df88255d381ee850dfb", "hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob("*.py"))}}
    (output / "build.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "hashes": {k: v for k, v in result["hashes"].items() if k in {"ollama_proxy_server.py", "qa_task_plan.py", "qa_document_knowledge.py", "qa_prompt_sources.py"}}}))


if __name__ == "__main__":
    main()
