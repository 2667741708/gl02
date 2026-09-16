"""Extend reviewed guarded templates for typed simple reads in document compounds."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def write(path, text): path.write_text(text, encoding="utf-8", newline="\n")

def main():
    for name in ("remote_guarded_deploy_qa_routing_v3_8093.ps1", "record_qa_routing_v3_version.ps1", "remote_preflight_qa_routing_v3.ps1", "verify_qa_routing_release.ps1"):
        path = ROOT / "tools" / name
        text = path.read_text(encoding="utf-8")
        if "'V13'" in text: raise ValueError("V13 already extended")
        text = text.replace("'V11','V12')", "'V11','V12','V13')")
        if name == "remote_guarded_deploy_qa_routing_v3_8093.ps1":
            text = text.replace("if ($StageRoot -ne $ExpectedStage)", "if ($Version -eq 'V13') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n    $Allowed = @('高炉前端数据/智能助手/backend/ollama_proxy_server.py', '高炉前端数据/智能助手/backend/qa_document_compound.py')\n}\nif ($StageRoot -ne $ExpectedStage)", 1)
        elif name == "record_qa_routing_v3_version.ps1":
            start = text.index("if ($Version -eq 'V12') {")
            end = text.index("\n}",start)+2
            text = text[:end]+"\n"+text[start:end].replace("V12","V13").replace("v12","v13").replace("isolate formal subtasks and preserve readable facts through tool failures", "render typed current readings in isolated formal compounds")+text[end:]
        elif name == "remote_preflight_qa_routing_v3.ps1":
            text = text.replace("$Python = ", "if ($Version -eq 'V13') { $StageRoot = 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\qa-routing-v13-20260916-r1' }\n$Python = ",1)
        write(path,text)
    path = ROOT / "tools/prepare_qa_routing_v3_release.py"
    text = path.read_text(encoding="utf-8").replace('"v11", "v12")','"v11", "v12", "v13")')
    text = text.replace('"v12": V12_ARTIFACTS}', '"v12": V12_ARTIFACTS, "v13": V13_ARTIFACTS}')
    text = text.replace('\ndef sha256(', '''
V13_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline":["8079f738da99e07332d8db8d9d536d87f5dac46dcee2c7cd1505f9a7cf8a5a66"],"markers":["qa_document_compound.prefetch_plan(prepared)"],"allow_create":False},
    "qa_document_compound.py": {"baseline":["eb4fb12d8bfe9d6e1c378bf1f41cce5688d6eb33fc879ff4657e382d83213ac6"],"markers":["qa-document-compound-v2", "def prefetch_plan"],"allow_create":False},
}

def sha256(''',1)
    text = text.replace('if args.version == "v12":\n            READ_SET.pop', 'if args.version in ("v12", "v13"):\n            READ_SET.pop',1)
    text = text.replace('    base_head = args.base_head.lower()', '''        if args.version == "v13":
            READ_SET.update({
                "高炉前端数据/智能助手/backend/qa_document_knowledge.py":"89109c1230a161064259bc9c98ee76e0a2dc2fca1461880fe3a45e86d95cd30b",
                "高炉前端数据/智能助手/backend/qa_evidence_policy.py":"9ec4132ca8075ee9757663eedbab99aa793f330ebb0133880d57ece4fec7fe26",
                "高炉前端数据/智能助手/backend/mcp_tool_selection.py":"2a0b8c8cc33444ef4f5138b23571a736a558229d9f7f09f0d88b735887235111",
                "高炉前端数据/智能助手/backend/qa_tool_fallback.py":"8d5c3737d463aa5990f844655d0925314eb77fc67a83c066e2a4bfd51c3043ab",
                "高炉前端数据/智能助手/backend/mcp_host/cross_source_plan.py":"c55458a75a362aaeb4eb91ac99d19dcbe130897779fb800b498bedf760bf92e1",
            })
    base_head = args.base_head.lower()''',1)
    text = text.replace('        write_json(release / "release-spec.json", spec)', '''        if args.version == "v13":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v13_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_document_compound.py", "tests/test_qa_v12_safety.py", "tests/test_qa_release_readiness.py")]
            validations[0]["evidence"] = "63 focused tests: compound typed current reads, risk/analysis negative gates, units/time/source/object identity and existing document/owner contracts"
            validations.append({"id":"release-get-readiness-faults","kind":"deterministic","status":"passed","evidence":"4 actual PowerShell gate tests: immediate/delayed/persistent/exception, maximum 3 GETs, no POST, no secret output"})
        write_json(release / "release-spec.json", spec)''',1)
    write(path,text)
    path = ROOT / "tools/prepare_qa_v9_invocations.py"
    write(path,path.read_text(encoding="utf-8").replace('"v11", "v12")','"v11", "v12", "v13")'))

if __name__ == "__main__": main()
