"""Use typed current-read results in document compounds from exact accepted V12."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proxy = ROOT / ".codex_runtime/qa-routing-v12/candidate/ollama_proxy_server.py"
    if hashlib.sha256(proxy.read_bytes()).hexdigest() != "8079f738da99e07332d8db8d9d536d87f5dac46dcee2c7cd1505f9a7cf8a5a66": raise ValueError("Accepted V12 proxy changed")
    text = proxy.read_text(encoding="utf-8")
    seam = 'qa_verified_facts.prefetch_outcome(prepared.get("mcp_prefetch") or {}, prepared["hidden_context"].get("qa_task_plan") or {})'
    if text.count(seam) != 2: raise ValueError("Two current read response seams required")
    text = text.replace(seam, 'qa_verified_facts.prefetch_outcome(prepared.get("mcp_prefetch") or {}, qa_document_compound.prefetch_plan(prepared))')
    ast.parse(text)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "ollama_proxy_server.py").write_text(text, encoding="utf-8", newline="\n")
    shutil.copyfile(ROOT / "高炉前端数据/智能助手/backend/qa_document_compound.py", args.output / "qa_document_compound.py")
    print(json.dumps({"ok":True, "hashes":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.glob("*.py")}}))

if __name__ == "__main__": main()
