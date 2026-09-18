"""Build opt-in turn projection from exact accepted V9/V10 proxy bytes."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "0d8698ffb39a5c319c44f4c21ae0235c1f8b8b4a573f004dbbbb495aedc650ec"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = ROOT / ".codex_runtime/qa-routing-v9/candidate/ollama_proxy_server.py"
    if hashlib.sha256(baseline.read_bytes()).hexdigest() != BASELINE:
        raise ValueError("Accepted proxy changed")
    before = baseline.read_text(encoding="utf-8")
    source = before.replace("import qa_document_knowledge\n", "import qa_document_knowledge\nimport qa_response_projection\n", 1)
    seam = '                "owner_subject": owner_subject,\n                "history_result": history_result,'
    if source.count(seam) != 1: raise ValueError("prepared seam changed")
    source = source.replace(seam, '                "owner_subject": owner_subject,\n                "user_message_id": user_message_id,\n                "response_projection": "turn" if payload.get("response_projection") == "turn" else "conversation",\n                "history_result": history_result,', 1)
    for spaces in (16, 20):
        pad = " " * spaces
        seam = "\n" + pad + "add_message(\n" + pad + "    conn,\n" + pad + '    prepared["conversation_id"],\n' + pad + '    "assistant",'
        expected = 2 if spaces == 16 else 1
        if source.count(seam) != expected: raise ValueError("assistant persistence seam changed")
        source = source.replace(seam, "\n" + pad + "assistant_message_id = add_message(\n" + pad + "    conn,\n" + pad + '    prepared["conversation_id"],\n' + pad + '    "assistant",')
    seam = '"messages": load_messages(conn, prepared["conversation_id"]),'
    if source.count(seam) != 3: raise ValueError("final messages seam changed")
    source = source.replace(seam, '"messages": (qa_response_projection.load_turn_messages(conn, prepared, assistant_message_id) if prepared.get("response_projection") == "turn" else load_messages(conn, prepared["conversation_id"])),\n                        "messages_projection": prepared.get("response_projection", "conversation"),')
    ast.parse(source)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "ollama_proxy_server.py").write_text(source, encoding="utf-8", newline="\n")
    shutil.copyfile(ROOT / "高炉前端数据/智能助手/backend/qa_response_projection.py", args.output / "qa_response_projection.py")
    (args.output / "proxy.patch").write_text("".join(difflib.unified_diff(before.splitlines(True), source.splitlines(True), fromfile="accepted-v10", tofile="routing-v11")), encoding="utf-8", newline="\n")
    print(json.dumps({"ok":True,"hashes":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.glob("*.py")}}))

if __name__ == "__main__": main()
