"""Prepare the single-module V17 release recipe; no remote operations."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def replace_one(path, old, new):
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise ValueError('Reviewed release seam changed: ' + str(path))
    path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')


def main():
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v17' in recipes:
        raise ValueError('V17 recipe already created; do not replay preparation')
    reads = dict(recipes['v16']['read_files'])
    reads['高炉前端数据/智能助手/backend/ollama_proxy_server.py'] = '3e535565e7579b4f33a29faf5938092d4b2b84708fa3dd410ff4ba8d4c6d50b6'
    recipes['v17'] = {
        'artifacts': {'qa_history_compound.py': {
            'baseline': ['b363bd8e2d127cb74fb3d33120e7eb9acd1eb2c9f992d84244e26599ddd09687'],
            'markers': ['qa-history-compound-v2', 'def normalize_present', 'revalidated_latest_tool_payload'],
            'allow_create': False}},
        'read_files': reads,
        'sources': ['tools/qa_routing_release_extensions.json', 'tools/extend_qa_release_v17.py',
                    'tools/prepare_qa_routing_v3_release.py', 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1',
                    'tools/record_qa_routing_v3_version.ps1', 'tools/remote_preflight_qa_routing_v3.ps1',
                    'tools/verify_qa_routing_release.ps1', '高炉前端数据/智能助手/backend/qa_history_compound.py',
                    'tests/test_qa_history_completion.py', 'tests/test_qa_history_compound.py',
                    'tests/test_qa_history_compound_seams.py'],
        'validations': [{'id': 'focused-pytest', 'kind': 'deterministic', 'status': 'passed',
                         'evidence': '133 focused tests including 21 legacy-completion and typed latest-result counterexamples'},
                        {'id': 'remote-readonly-preflight', 'kind': 'readonly_remote', 'status': 'pending'}]}
    # Keep the reviewed historic V16 recipe intact; add an exact V17 allowlist.
    for name in ('remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1',
                 'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1'):
        path = ROOT / 'tools' / name
        replace_one(path, "'V15','V16')", "'V15','V16','V17')")
    path = ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1'
    replace_one(path, "if ($StageRoot -ne $ExpectedStage)",
                "if ($Version -eq 'V17') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
                "    $Allowed = @('高炉前端数据/智能助手/backend/qa_history_compound.py')\n}\n"
                "if ($StageRoot -ne $ExpectedStage)")
    path = ROOT / 'tools/record_qa_routing_v3_version.ps1'
    replace_one(path, '$Operation = Get-Content',
                "if ($Version -eq 'V17') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
                "    $ExecutionId = 'qa-routing-v17-20260916-r1'\n"
                "    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v17-20260916-r1'\n"
                "    $CommitMessage = 'fix: validate mixed history subtask completion [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v17-20260916-r1]'\n"
                "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n"
                "    $OperationPath = Join-Path $StageRoot 'operation.json'\n"
                "    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    path = ROOT / 'tools/remote_preflight_qa_routing_v3.ps1'
    replace_one(path, "if ($Version -eq 'V16') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v16-20260916-r1' }",
                "if ($Version -eq 'V16') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v16-20260916-r1' }\n"
                "if ($Version -eq 'V17') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v17-20260916-r1' }")
    replace_one(ROOT / 'tools/prepare_qa_v9_invocations.py', '"v15", "v16")', '"v15", "v16", "v17")')
    registry.write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    candidate = ROOT / '.codex_runtime/qa-routing-v17/candidate'
    candidate.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(ROOT / '高炉前端数据/智能助手/backend/qa_history_compound.py', candidate / 'qa_history_compound.py')
    print(json.dumps({'ok': True, 'version': 'v17', 'target_count': 1}))


if __name__ == '__main__': main()
