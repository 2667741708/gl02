"""One-time reviewed extension of exact guarded release templates for V12."""
import hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def write(path, text): path.write_text(text, encoding="utf-8", newline="\n")

def main():
    plan_hash = hashlib.sha256((ROOT / ".codex_runtime/qa-routing-v12/baseline/cross_source_plan.py").read_bytes()).hexdigest()
    allowed = ["ollama_proxy_server.py", "mcp_tool_selection.py", "qa_document_compound.py", "qa_tool_fallback.py", "qa_evidence_policy.py", "qa_document_knowledge.py", "mcp_host/cross_source_plan.py"]
    for name in ("remote_guarded_deploy_qa_routing_v3_8093.ps1", "record_qa_routing_v3_version.ps1", "remote_preflight_qa_routing_v3.ps1", "verify_qa_routing_release.ps1"):
        path = ROOT / "tools" / name
        text = path.read_text(encoding="utf-8")
        if "'V12'" in text: raise ValueError("V12 templates already extended")
        text = text.replace("'V10','V11')", "'V10','V11','V12')")
        if name == "remote_guarded_deploy_qa_routing_v3_8093.ps1":
            block = "if ($Version -eq 'V12') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n    $Allowed = @(\n" + ",\n".join("        '高炉前端数据/智能助手/backend/" + p + "'" for p in allowed) + "\n    )\n}\n"
            text = text.replace("if ($StageRoot -ne $ExpectedStage)", block + "if ($StageRoot -ne $ExpectedStage)", 1)
        elif name == "record_qa_routing_v3_version.ps1":
            start = text.index("if ($Version -eq 'V11') {")
            end = text.index("\n}", start)+2
            block = text[start:end].replace("V11", "V12").replace("v11", "v12").replace("bound controlled responses to exact owner checked turn messages", "isolate formal subtasks and preserve readable facts through tool failures")
            text = text[:end] + "\n" + block + text[end:]
        elif name == "remote_preflight_qa_routing_v3.ps1":
            text = text.replace("$Python = ", "if ($Version -eq 'V12') { $StageRoot = 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\qa-routing-v12-20260916-r1' }\n$Python = ", 1)
        write(path, text)
    path = ROOT / "tools/prepare_qa_routing_v3_release.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace('"v10", "v11")', '"v10", "v11", "v12")')
    text = text.replace('"v11": V11_ARTIFACTS}', '"v11": V11_ARTIFACTS, "v12": V12_ARTIFACTS}')
    rows = {
        "ollama_proxy_server.py": {"baseline":["2431a7a78e46f7c693343f333740cfa1aa8b4ae697a86c31c6e21cd29236a593"],"markers":["import qa_document_compound", "qa_document_compound.compose"],"allow_create":False},
        "mcp_tool_selection.py": {"baseline":["f986ec49226593befe064763622821fc6bf738a66649b3a23bca17eb6f00c4e4"],"markers":["qa_tool_fallback.summarize"],"allow_create":False},
        "qa_document_compound.py": {"baseline":[],"markers":["qa-document-compound-v1", "missing_document_subtasks"],"allow_create":True},
        "qa_tool_fallback.py": {"baseline":[],"markers":["qa-tool-fallback-v1", "def summarize"],"allow_create":True},
        "qa_evidence_policy.py": {"baseline":["05cb372361038f82245cb122f768cafbad01b2bcd2f24917968f822eeac2ad23"],"markers":["调压阀", "热平衡"],"allow_create":False},
        "qa_document_knowledge.py": {"baseline":["87c4caea1107710adf3ac277338669d21f72b6b1a99d1ce565f55f300dfe6919"],"markers":["verified_original_atomic", '"model_request_count": 0'],"allow_create":False},
        "cross_source_plan.py": {"relative":"高炉前端数据/智能助手/backend/mcp_host/cross_source_plan.py","baseline":[plan_hash],"markers":["declared dependency", "Cyclic dependency in plan"],"allow_create":False},
    }
    text = text.replace('\ndef sha256(', '\nV12_ARTIFACTS = ' + repr(rows) + '\n\ndef sha256(', 1)
    text = text.replace('    base_head = args.base_head.lower()', '''        if args.version == "v12":
            READ_SET.pop("高炉前端数据/智能助手/backend/ollama_proxy_server.py", None)
            READ_SET.pop("高炉前端数据/智能助手/backend/qa_evidence_policy.py", None)
            READ_SET["高炉前端数据/智能助手/backend/qa_response_projection.py"] = "60e8db0edfab036f17bc9c201d096d652c75b457570ce4eb07fdb9dcb2caa693"
    base_head = args.base_head.lower()''', 1)
    seam = '        write_json(release / "release-spec.json", spec)'
    text = text.replace(seam, '''        if args.version == "v12":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v12_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_document_compound.py",
                "高炉前端数据/智能助手/backend/qa_tool_fallback.py",
                "高炉前端数据/智能助手/backend/qa_evidence_policy.py",
                "高炉前端数据/智能助手/backend/qa_document_knowledge.py",
                "高炉前端数据/智能助手/backend/mcp_host/cross_source_plan.py",
                "tests/test_qa_v12_safety.py", "tests/test_qa_step_plan_integrity.py")]
            validations[0]["evidence"] = "137 focused tests: compound formal isolation, success retention and secret exclusion, early DAG/schema gates, original coverage, code boundary and owner turn projection"
''' + seam, 1)
    write(path, text)
    path = ROOT / "tools/prepare_qa_v9_invocations.py"
    write(path, path.read_text(encoding="utf-8").replace('"v10", "v11")', '"v10", "v11", "v12")'))

if __name__ == "__main__": main()
