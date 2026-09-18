"""Register the exact one-module exclusive-use release; no remote operations."""
import hashlib
import json
from pathlib import Path
import shutil

from extend_qa_release_v17 import replace_one

ROOT = Path(__file__).resolve().parents[1]
REL = '高炉前端数据/智能助手/backend/qa_request_control.py'


def main():
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v21' in recipes:
        raise ValueError('V21 already registered; do not replay preparation')
    baseline = ROOT / '.codex_runtime/qa-routing-v21/baseline/qa_request_control.py'
    digest = hashlib.sha256(baseline.read_bytes()).hexdigest()
    if digest != '0853b77655247030436f0a55a9c973503dc6a853280f3f9aa09d28be6cbeb901':
        raise ValueError('Reviewed production baseline changed')
    reads = dict(recipes['v20']['read_files'])
    reads.pop(REL)
    reads['高炉前端数据/智能助手/backend/ollama_proxy_server.py'] = '38c99c5fbde8e967549f0435a608b92db5648520a3e37622b686a391c004deb2'
    recipes['v21'] = {
        'artifacts': {'qa_request_control.py': {'baseline': [digest],
            'markers': ['assistant_in_use', 'automatic_replay', 'old.finished.is_set()'],
            'allow_create': False}},
        'read_files': reads,
        'sources': ['tools/qa_routing_release_extensions.json', 'tools/extend_qa_release_v21.py',
            'tools/prepare_qa_routing_v3_release.py', 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1',
            'tools/record_qa_routing_v3_version.ps1', 'tools/remote_preflight_qa_routing_v3.ps1',
            'tools/verify_qa_routing_release.ps1', REL, 'tests/test_qa_exclusive_use.py'],
        'validations': [{'id': 'focused-pytest', 'kind': 'deterministic', 'status': 'passed',
                         'evidence': '35 associated tests;9 exclusive role-pair/cancel/failure/race tests'},
                        {'id': 'remote-readonly-preflight', 'kind': 'readonly_remote', 'status': 'pending'}]}
    for name in ('remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1',
                 'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1'):
        replace_one(ROOT/'tools'/name, "'V19','V20')", "'V19','V20','V21')")
    replace_one(ROOT/'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1', 'if ($StageRoot -ne $ExpectedStage)',
        "if ($Version -eq 'V21') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $Allowed = @('高炉前端数据/智能助手/backend/qa_request_control.py')\n}\nif ($StageRoot -ne $ExpectedStage)")
    replace_one(ROOT/'tools/record_qa_routing_v3_version.ps1', '$Operation = Get-Content',
        "if ($Version -eq 'V21') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $ExecutionId = 'qa-routing-v21-20260916-r1'\n"
        "    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v21-20260916-r1'\n"
        "    $CommitMessage = 'fix: enforce one active assistant request across roles [REQ-QA-EXCLUSIVE-USE-20260916] [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v21-20260916-r1]'\n"
        "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n"
        "    $OperationPath = Join-Path $StageRoot 'operation.json'\n"
        "    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    replace_one(ROOT/'tools/remote_preflight_qa_routing_v3.ps1', "$Python = 'C:\\Program Files\\Python311\\python.exe'",
        "if ($Version -eq 'V21') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v21-20260916-r1' }\n$Python = 'C:\\Program Files\\Python311\\python.exe'")
    replace_one(ROOT/'tools/prepare_qa_v9_invocations.py', '"v19", "v20")', '"v19", "v20", "v21")')
    replace_one(ROOT/'tools/stage_qa_release.py', "('v18', 'v19', 'v20')", "('v18', 'v19', 'v20', 'v21')")
    registry.write_bytes((json.dumps(recipes,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    candidate = ROOT/'.codex_runtime/qa-routing-v21/candidate'
    candidate.mkdir(exist_ok=False)
    shutil.copyfile(ROOT/REL, candidate/'qa_request_control.py')
    print(json.dumps({'ok': True, 'version': 'v21', 'targets': [REL]}))


if __name__ == '__main__': main()
