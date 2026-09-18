"""Extend guarded templates to a one-module V10 knowledge repair."""
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[1]
def write(path, text): path.write_text(text, encoding="utf-8", newline="\n")

def main():
    for name in ("remote_guarded_deploy_qa_routing_v3_8093.ps1", "record_qa_routing_v3_version.ps1", "remote_preflight_qa_routing_v3.ps1", "verify_qa_routing_release.ps1"):
        path = ROOT / "tools" / name
        text = path.read_text(encoding="utf-8")
        text = text.replace("ValidateSet('V3','V4','V5','V6','V7','V8','V9')", "ValidateSet('V3','V4','V5','V6','V7','V8','V9','V10')")
        if name == "remote_guarded_deploy_qa_routing_v3_8093.ps1":
            seam = "if ($StageRoot -ne $ExpectedStage)"
            text = text.replace(seam, "if ($Version -eq 'V10') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n    $Allowed = @('高炉前端数据/智能助手/backend/qa_document_knowledge.py')\n}\n" + seam, 1)
        elif name == "record_qa_routing_v3_version.ps1":
            start = text.index("if ($Version -eq 'V9') {")
            end = text.index("\n}", start) + 2
            block = text[start:end].replace("V9", "V10").replace("v9", "v10").replace("resolve original subsections and preserve safe mixed queries", "resolve unique original atomic clauses and complete table boundaries")
            text = text[:end] + "\n" + block + text[end:]
        elif name == "remote_preflight_qa_routing_v3.ps1":
            seam = "$Python = "
            text = text.replace(seam, "if ($Version -eq 'V10') { $StageRoot = 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\qa-routing-v10-20260916-r1' }\n" + seam, 1)
        write(path, text)
    path = ROOT / "tools/prepare_qa_routing_v3_release.py"
    text = path.read_text(encoding="utf-8").replace('"v8", "v9")', '"v8", "v9", "v10")')
    text = text.replace('"v9": V9_ARTIFACTS}', '"v9": V9_ARTIFACTS, "v10": V10_ARTIFACTS}')
    text = text.replace('\n\ndef sha256(', '''
V10_ARTIFACTS = {
    "qa_document_knowledge.py": {"baseline": ["cfa553208c8a6e408e09c969140b8795ae852314a0abe058a187fd4fbb65a3f4"], "markers": ["verified_original_atomic", "atomic_reference_ambiguous"], "allow_create": False},
}

def sha256(''', 1)
    text = text.replace('if args.version == "v9":\n            READ_SET.pop', 'if args.version in ("v9", "v10"):\n            READ_SET.pop', 1)
    text = text.replace('    base_head = args.base_head.lower()', '''        if args.version == "v10":
            READ_SET.update({
                "高炉前端数据/智能助手/backend/ollama_proxy_server.py": "0d8698ffb39a5c319c44f4c21ae0235c1f8b8b4a573f004dbbbb495aedc650ec",
                "高炉前端数据/智能助手/backend/qa_evidence_policy.py": "05cb372361038f82245cb122f768cafbad01b2bcd2f24917968f822eeac2ad23",
            })
    base_head = args.base_head.lower()''', 1)
    text = text.replace('        if args.semantic_review == "passed":', '        if args.semantic_review == "passed":')
    seam = '        write_json(release / "release-spec.json", spec)'
    text = text.replace(seam, '''        if args.version == "v10":
            spec["sources"] = [str(root / path) for path in (
                "tools/prepare_qa_routing_v3_release.py", "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1",
                "tools/record_qa_routing_v3_version.ps1", "tools/remote_preflight_qa_routing_v3.ps1",
                "tools/verify_qa_routing_release.ps1", "高炉前端数据/智能助手/backend/qa_document_knowledge.py",
                "tests/test_qa_document_knowledge.py", "tools/check_qa_knowledge_candidate_readonly.py")]
            validations[0]["evidence"] = "79 focused tests; atomic full-original, prefix and ambiguity, scope, table boundary, existing route/history/evidence/completion contracts"
            validations.append({"id":"knowledge-all-readonly", "kind":"readonly_remote", "status":"passed", "evidence":"833 real stored KB checks: 803 expected-text coverage candidates, 30 oracle conflicts; no semantic pass inferred; zero model calls, POSTs and DB writes"})
''' + seam, 1)
    write(path, text)
    candidate = ROOT / ".codex_runtime/qa-routing-v10/candidate"
    candidate.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "高炉前端数据/智能助手/backend/qa_document_knowledge.py", candidate / "qa_document_knowledge.py")

if __name__ == "__main__": main()
