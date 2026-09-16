"""Register the production-derived statistical-scope release; local operations only."""
import difflib
import hashlib
import json
from pathlib import Path

from extend_qa_release_v17 import replace_one
from build_qa_routing_v22_candidate import BASELINES

ROOT = Path(__file__).resolve().parents[1]
BACKEND = '高炉前端数据/智能助手/backend/'


def main():
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v22' in recipes:
        raise ValueError('V22 already registered; do not replay preparation')
    runtime = ROOT / '.codex_runtime/qa-routing-v22'
    markers = {
        'ollama_proxy_server.py': ['qa_verified_facts.trend_context', 'qa_verified_facts.render_cv', '全窗口趋势'],
        'qa_verified_facts.py': ['qa-verified-facts-v2-statistical-scope', 'def cv_contract', 'def trend_context'],
        'qa_evidence_policy.py': ['qa-evidence-no-code-v5', '协议本身自动保障安全', 'def enforce_no_code'],
    }
    reads = dict(recipes['v21']['read_files'])
    artifacts = {}
    diff = []
    for name, expected in BASELINES.items():
        baseline = (runtime / 'baseline' / name).read_bytes()
        if hashlib.sha256(baseline).hexdigest() != expected:
            raise ValueError('Production baseline changed: ' + name)
        desired = (runtime / 'candidate' / name).read_text(encoding='utf-8')
        if any(marker not in desired for marker in markers[name]):
            raise ValueError('Candidate marker missing: ' + name)
        artifacts[name] = {'baseline': [expected], 'markers': markers[name], 'allow_create': False}
        reads.pop(BACKEND + name, None)
        diff.extend(difflib.unified_diff(baseline.decode('utf-8').splitlines(True), desired.splitlines(True),
                                       fromfile='production/' + name, tofile='candidate/' + name))
    reads[BACKEND + 'qa_request_control.py'] = '3a377273d67767727432744a1e2077df42a6516a4801042f02f6df34fbbd41ca'
    scripts = ['remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1',
               'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1']
    recipes['v22'] = {
        'artifacts': artifacts, 'read_files': reads,
        'sources': ['tools/qa_routing_release_extensions.json', 'tools/extend_qa_release_v22.py',
                    'tools/build_qa_routing_v22_candidate.py', 'tools/prepare_qa_routing_v3_release.py',
                    *['tools/' + name for name in scripts],
                    *[BACKEND + name for name in BASELINES if name != 'ollama_proxy_server.py'],
                    'tests/test_qa_statistical_scope.py'],
        'validations': [{'id': 'focused-pytest', 'kind': 'deterministic', 'status': 'passed',
                         'evidence': '40 tests passed; synthetic baseline/candidate renderer comparison'},
                        {'id': 'remote-readonly-preflight', 'kind': 'readonly_remote', 'status': 'pending'}],
    }
    for name in scripts:
        replace_one(ROOT / 'tools' / name, "'V20','V21')", "'V20','V21','V22')")
    targets = ','.join("'" + BACKEND + name + "'" for name in BASELINES)
    replace_one(ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1', 'if ($StageRoot -ne $ExpectedStage)',
                "if ($Version -eq 'V22') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
                + '    $Allowed = @(' + targets + ')\n}\nif ($StageRoot -ne $ExpectedStage)')
    replace_one(ROOT / 'tools/record_qa_routing_v3_version.ps1', '$Operation = Get-Content',
                "if ($Version -eq 'V22') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
                "    $ExecutionId = 'qa-routing-v22-20260916-r1'\n"
                "    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v22-20260916-r1'\n"
                "    $CommitMessage = 'fix: validate CV domain and clarify trend scope [REQ-QA-STATISTICAL-SCOPE-20260917] [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v22-20260916-r1]'\n"
                "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n"
                "    $OperationPath = Join-Path $StageRoot 'operation.json'\n"
                "    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    replace_one(ROOT / 'tools/remote_preflight_qa_routing_v3.ps1', "$Python = 'C:\\Program Files\\Python311\\python.exe'",
                "if ($Version -eq 'V22') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v22-20260916-r1' }\n$Python = 'C:\\Program Files\\Python311\\python.exe'")
    replace_one(ROOT / 'tools/prepare_qa_v9_invocations.py', '"v20", "v21")', '"v20", "v21", "v22")')
    replace_one(ROOT / 'tools/stage_qa_release.py', "'v20', 'v21')", "'v20', 'v21', 'v22')")
    registry.write_bytes((json.dumps(recipes, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    (runtime / 'candidate.diff').write_bytes(''.join(diff).encode('utf-8'))
    print(json.dumps({'ok': True, 'version': 'v22', 'targets': list(artifacts), 'read_count': len(reads)}))


if __name__ == '__main__':
    main()
