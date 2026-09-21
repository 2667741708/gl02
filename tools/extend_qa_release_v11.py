"""Extend guarded release templates for opt-in current-turn projection."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def write(path, text): path.write_text(text, encoding="utf-8", newline="\n")

def main():
    for name in ("remote_guarded_deploy_qa_routing_v3_8093.ps1", "record_qa_routing_v3_version.ps1", "remote_preflight_qa_routing_v3.ps1", "verify_qa_routing_release.ps1"):
        path = ROOT / "tools" / name
        text = path.read_text(encoding="utf-8").replace("ValidateSet('V3','V4','V5','V6','V7','V8','V9','V10')", "ValidateSet('V3','V4','V5','V6','V7','V8','V9','V10','V11')")
        if name == "remote_guarded_deploy_qa_routing_v3_8093.ps1":
            seam = "if ($StageRoot -ne $ExpectedStage)"
            text = text.replace(seam, "if ($Version -eq 'V11') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n    $Allowed = @('高炉前端数据/智能助手/backend/ollama_proxy_server.py', '高炉前端数据/智能助手/backend/qa_response_projection.py')\n}\n" + seam, 1)
        elif name == "record_qa_routing_v3_version.ps1":
            start = text.index("if ($Version -eq 'V10') {")
            end = text.index("\n}", start) + 2
            block = text[start:end].replace("V10", "V11").replace("v10", "v11").replace("resolve unique original atomic clauses and complete table boundaries", "bound controlled responses to exact owner checked turn messages")
            text = text[:end] + "\n" + block + text[end:]
        elif name == "remote_preflight_qa_routing_v3.ps1":
            text = text.replace("$Python = ", "if ($Version -eq 'V11') { $StageRoot = 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\qa-routing-v11-20260916-r1' }\n$Python = ", 1)
        write(path, text)
    path = ROOT / "tools/prepare_qa_routing_v3_release.py"
    text = path.read_text(encoding="utf-8").replace('"v9", "v10")', '"v9", "v10", "v11")')
    text = text.replace('"v10": V10_ARTIFACTS}', '"v10": V10_ARTIFACTS, "v11": V11_ARTIFACTS}')
    text = text.replace('\n\ndef sha256(', '''
V11_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline": ["0d8698ffb39a5c319c44f4c21ae0235c1f8b8b4a573f004dbbbb495aedc650ec"], "markers": ["import qa_response_projection", "messages_projection"], "allow_create": False},
    "qa_response_projection.py": {"baseline": [], "markers": ["qa-response-projection-v1", "c.owner_subject = ?", "turn messages do not match owner and role"], "allow_create": True},
}

def sha256(''', 1)
    text = text.replace('if args.version == "v10":\n            READ_SET.update', 'if args.version in ("v10", "v11"):\n            READ_SET.update', 1)
    text = text.replace('    base_head = args.base_head.lower()', '''        if args.version == "v11":
            READ_SET.pop("高炉前端数据/智能助手/backend/ollama_proxy_server.py")
            READ_SET["高炉前端数据/智能助手/backend/qa_document_knowledge.py"] = "87c4caea1107710adf3ac277338669d21f72b6b1a99d1ce565f55f300dfe6919"
    base_head = args.base_head.lower()''', 1)
    seam = '        write_json(release / "release-spec.json", spec)'
    text = text.replace(seam, '''        if args.version == "v11":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v11_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_response_projection.py", "tests/test_qa_response_projection.py",
                "tools/run_qa_failed_retest_once.py", "tests/test_qa_retest_persistence.py")]
            validations[0]["evidence"] = "88 focused tests: exact owner/role/turn projection, history-free controlled payload and model-independent document readiness plus all V10 focused contracts"
''' + seam, 1)
    write(path, text)
    path = ROOT / "tools/prepare_qa_v9_invocations.py"
    write(path, path.read_text(encoding="utf-8").replace('choices=("v9", "v10")', 'choices=("v9", "v10", "v11")'))

if __name__ == "__main__": main()
