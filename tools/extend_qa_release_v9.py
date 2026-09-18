"""One-time, checked UTF-8/LF migration of reviewed release templates to V9."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def change(name, fn):
    path = ROOT / "tools" / name
    source = path.read_text(encoding="utf-8")
    result = fn(source)
    if result == source:
        raise ValueError(f"No change: {name}")
    path.write_text(result, encoding="utf-8", newline="\n")

def ps(source):
    return source.replace("ValidateSet('V3','V4','V5','V6','V7','V8')", "ValidateSet('V3','V4','V5','V6','V7','V8','V9')")

def deploy(source):
    source = ps(source)
    seam = "if ($StageRoot -ne $ExpectedStage)"
    return source.replace(seam, """if ($Version -eq 'V9') {
    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $Allowed = @(
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
        '高炉前端数据/智能助手/backend/qa_document_knowledge.py',
        '高炉前端数据/智能助手/backend/qa_evidence_policy.py'
    )
}
""" + seam, 1)

def record(source):
    source = ps(source)
    start = source.index("if ($Version -eq 'V8') {")
    end = source.index("\n}", start) + 2
    block = source[start:end].replace("V8", "V9").replace("v8", "v9").replace("verify original document scope and preserve permitted prompt evidence", "resolve original subsections and preserve safe mixed queries")
    return source[:end] + "\n" + block + source[end:]

def prepare(source):
    source = source.replace('"v7", "v8")', '"v7", "v8", "v9")')
    source = source.replace('"v8": V8_ARTIFACTS}', '"v8": V8_ARTIFACTS, "v9": V9_ARTIFACTS}')
    seam = '\n\ndef sha256('
    contracts = '''
V9_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline": ["7f8b79fbfa98db94f55d2c7c40f0a0749c953ba50a46448933929f2ee1ff7841"], "markers": ["qa_evidence_policy.apply_request_boundary", "stream_completed"], "allow_create": False},
    "qa_document_knowledge.py": {"baseline": ["b7a55145bdadd94f2659b0c63de04af01400e4b4c21992a1fbdbcb08747fb696"], "markers": ["verified_original_subsection", "def _original_subsection"], "allow_create": False},
    "qa_evidence_policy.py": {"baseline": ["0724e66578f521ba272867c06436da836111669d38356df9d939186cdb2e62e3"], "markers": ["def apply_request_boundary", "def boundary_result"], "allow_create": False},
}
'''
    source = source.replace(seam, '\n' + contracts + seam, 1)
    source = source.replace('if args.version == "v8":\n            READ_SET.pop', 'if args.version in ("v8", "v9"):\n            READ_SET.pop', 1)
    seam = '    base_head = args.base_head.lower()'
    source = source.replace(seam, '''        if args.version == "v9":
            READ_SET.pop("高炉前端数据/智能助手/backend/qa_evidence_policy.py")
            READ_SET.update({
                "高炉前端数据/智能助手/backend/qa_task_plan.py": "8b9fa2eec70c9fc6ce5d33e2ff1613231ef83072595fd99a94f1e1c700fc1fb1",
                "高炉前端数据/智能助手/backend/qa_prompt_sources.py": "14a175a44eb7dde107668ab78e803a56f305bdcfb10fc7c7fbfc820dbe258b3a",
            })
''' + seam, 1)
    seam = '        if args.semantic_review == "passed":'
    # Validation status is generated only after the caller has performed checks.
    start = source.index('        elif args.version == "v8":')
    end = source.index('\n        ', source.index('"tests/test_qa_document_knowledge.py")]', start) + 1)
    block = '''        elif args.version == "v9":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v9_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_document_knowledge.py", "高炉前端数据/智能助手/backend/qa_evidence_policy.py",
                "tests/test_qa_document_knowledge.py", "tests/test_qa_routing_v9_seams.py")]
'''
    source = source[:end] + '\n' + block.rstrip() + source[end:]
    return source

if __name__ == "__main__":
    change("remote_guarded_deploy_qa_routing_v3_8093.ps1", deploy)
    change("record_qa_routing_v3_version.ps1", record)
    change("remote_preflight_qa_routing_v3.ps1", lambda s: ps(s).replace("if ($Version -eq 'V8') { $StageRoot = 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\qa-routing-v8-20260916-r1' }", "if ($Version -eq 'V8') { $StageRoot = 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\qa-routing-v8-20260916-r1' }\nif ($Version -eq 'V9') { $StageRoot = 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\qa-routing-v9-20260916-r1' }"))
    change("verify_qa_routing_release.ps1", ps)
    change("prepare_qa_routing_v3_release.py", prepare)
