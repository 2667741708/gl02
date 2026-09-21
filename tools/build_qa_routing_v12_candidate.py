"""Hash-bound V12 seams: isolated formal subtasks, readable fallback, early DAG gates."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据/智能助手/backend"

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def replace_once(text, before, after):
    if text.count(before) != 1: raise ValueError("Accepted seam changed: " + before[:80])
    return text.replace(before, after, 1)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proxy = ROOT / ".codex_runtime/qa-routing-v11/candidate/ollama_proxy_server.py"
    selection = ROOT / ".codex_runtime/qa-routing-v12/baseline/mcp_tool_selection.py"
    if digest(proxy) != "2431a7a78e46f7c693343f333740cfa1aa8b4ae697a86c31c6e21cd29236a593": raise ValueError("Accepted V11 proxy changed")
    if digest(selection) != "f986ec49226593befe064763622821fc6bf738a66649b3a23bca17eb6f00c4e4": raise ValueError("Accepted tool contracts changed")
    args.output.mkdir(parents=True, exist_ok=True)
    before = proxy.read_text(encoding="utf-8")
    source = replace_once(before, "import qa_document_knowledge\n", "import qa_document_knowledge\nimport qa_document_compound\n")
    seam = '            knowledge_pack = ({"enabled": False, "evidence": [], "message": "本轮由核验原文执行器回答"} if document_result is not None else qa_search_knowledge('
    source = replace_once(source, seam,
        '            document_compound = (qa_document_compound.prepare(conn, question, task_plan) if str(payload.get("analysis_mode") or "") != "initial_context_explanation" else None)\n'
        '            if document_compound:\n'
        '                routing_question = document_compound["remainder_question"]\n'
        + seam.replace("if document_result is not None", "if document_result is not None or document_compound is not None"))
    start = source.index('                "messages": build_hidden_qa_messages(')
    end = source.index('                "bound_assistant_context": load_json', start)
    block = source[start:end]
    block = replace_once(block, '"messages": build_hidden_qa_messages(', '"messages": qa_document_compound.model_messages(build_hidden_qa_messages(')
    block = replace_once(block, '                ),\n', '                ), {"document_compound": document_compound}),\n')
    source = source[:start] + block + source[end:]
    source = replace_once(source, '                "document_result": document_result,', '                "document_result": document_result,\n                "document_compound": document_compound,')
    seam = 'tool_result = qa_evidence_policy.boundary_result(question, tool_result)'
    if source.count(seam) != 3: raise ValueError("Three final response paths required")
    lines = source.splitlines(True)
    for index in range(len(lines)-1, -1, -1):
        if seam in lines[index]:
            pad = lines[index][:len(lines[index])-len(lines[index].lstrip())]
            lines.insert(index+1, pad + 'answer, tool_result = qa_document_compound.compose(answer, tool_result, prepared)\n')
    source = "".join(lines)
    ast.parse(source)
    (args.output / "ollama_proxy_server.py").write_text(source, encoding="utf-8", newline="\n")
    (args.output / "proxy.patch").write_text("".join(difflib.unified_diff(before.splitlines(True), source.splitlines(True), fromfile="accepted-v11", tofile="routing-v12")), encoding="utf-8", newline="\n")
    text = selection.read_text(encoding="utf-8")
    text = replace_once(text, "from qa_evidence_claims import answer_numbers_are_grounded", "from qa_evidence_claims import answer_numbers_are_grounded\nimport qa_tool_fallback")
    start = text.index('    """Return a safe fallback', text.index("def deterministic_evidence_summary"))
    end = text.index("\n\ndef catalog_availability", start)
    text = text[:start] + '    """Preserve supported successful facts without exposing raw tool payloads."""\n    return qa_tool_fallback.summarize(results)\n' + text[end:]
    ast.parse(text)
    (args.output / "mcp_tool_selection.py").write_text(text, encoding="utf-8", newline="\n")
    for name in ("qa_document_compound.py", "qa_tool_fallback.py", "qa_evidence_policy.py", "qa_document_knowledge.py"):
        shutil.copyfile(BACKEND / name, args.output / name)
    shutil.copyfile(BACKEND / "mcp_host/cross_source_plan.py", args.output / "cross_source_plan.py")
    print(json.dumps({"ok":True, "hashes":{p.name:digest(p) for p in args.output.glob("*.py")}}))

if __name__ == "__main__": main()
