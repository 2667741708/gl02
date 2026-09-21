"""Register the three-file latest-read and no-code offer repair."""
import difflib
import hashlib
import json
import subprocess
from pathlib import Path

from extend_qa_release_v17 import replace_one

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '高炉前端数据/智能助手/backend/'
BASELINES = {
    'ollama_proxy_server.py': 'c90f82cf2466bf4004efed330d21a252fdd8c847605f966909102a9c7653aefc',
    'qa_verified_facts.py': '51112c7f8b7de36dab6ce49046968921ce3194adc1348005f4a8c09d73dbcde6',
    'qa_evidence_policy.py': 'd4e44deda3df4740620a9baa6c880023f28fe8683b228015c519ae240c3d769d',
}


def main():
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v24' in recipes:
        raise ValueError('V24 already registered')
    runtime = ROOT / '.codex_runtime/qa-routing-v24'
    baseline_dir = runtime / 'baseline'
    baseline_dir.mkdir(exist_ok=False)
    changes = []
    for name, expected in BASELINES.items():
        if name == 'ollama_proxy_server.py':
            baseline = (ROOT / '.codex_runtime/qa-routing-v22/candidate' / name).read_bytes()
        else:
            baseline = subprocess.check_output(['git', 'show', 'HEAD:' + PREFIX + name], cwd=ROOT)
        if hashlib.sha256(baseline).hexdigest() != expected:
            raise ValueError('Production baseline mismatch: ' + name)
        desired = (runtime / 'candidate' / name).read_bytes()
        (baseline_dir / name).write_bytes(baseline)
        changes.extend(difflib.unified_diff(baseline.decode().splitlines(True), desired.decode().splitlines(True),
            fromfile='production/' + name, tofile='candidate/' + name))
    (runtime / 'candidate.diff').write_bytes(''.join(changes).encode('utf-8'))
    reads = dict(recipes['v23']['read_files'])
    for name in BASELINES:
        reads.pop(PREFIX + name)
    reads[PREFIX + 'qa_task_plan.py'] = '0a1b950f221dcf90c03e1e623fe17453e7d3551ae2d9cf5bb789d9fd9c952d64'
    scripts = ['remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1',
        'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1']
    markers = {
        'ollama_proxy_server.py': ['REQ-QA-LATEST-PREFETCH-REUSE-20260917', 'qa_verified_facts.reusable_latest_read'],
        'qa_verified_facts.py': ['qa-verified-facts-v3-latest-reuse', 'def reusable_latest_read', 'def prefetch_outcome'],
        'qa_evidence_policy.py': ['qa-evidence-no-code-v6-offer-boundary', 'def enforce_no_code'],
    }
    recipes['v24'] = {
        'artifacts': {name: {'baseline': [value], 'markers': markers[name], 'allow_create': False}
            for name, value in BASELINES.items()},
        'read_files': reads,
        'sources': ['tools/extend_qa_release_v24.py', 'tools/build_qa_v24_latest_candidate.py',
            'tools/qa_routing_release_extensions.json', 'tools/prepare_qa_routing_v3_release.py',
            'tools/stage_qa_release.py', 'tools/prepare_qa_v9_invocations.py', 'tools/record_qa_release_preflight.py',
            *['tools/' + name for name in scripts], PREFIX + 'qa_verified_facts.py', PREFIX + 'qa_evidence_policy.py',
            'tests/test_qa_latest_reuse_and_code_offers.py', 'tests/test_qa_evidence_policy.py', 'tests/test_qa_statistical_scope.py'],
        'validations': [
            {'id': 'focused-pytest', 'kind': 'deterministic', 'status': 'passed', 'evidence': '76 passed; latest read coverage, historical/analysis negatives, actual proxy seam, no-code offers and legal arithmetic'},
            {'id': 'final-luna-diff-review', 'kind': 'semantic', 'status': 'passed', 'evidence': 'gpt-5.6-luna low reviewed final helper exclusion expansion and candidate-required fail-closed gate'},
            {'id': 'remote-readonly-preflight', 'kind': 'readonly_remote', 'status': 'pending'},
        ],
    }
    for name in scripts:
        replace_one(ROOT / 'tools' / name, "'V21','V22','V23')", "'V21','V22','V23','V24')")
    allowed = ','.join("'" + PREFIX + name + "'" for name in BASELINES)
    replace_one(ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1', 'if ($StageRoot -ne $ExpectedStage)',
        "if ($Version -eq 'V24') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n    $Allowed = @(" + allowed + ")\n}\nif ($StageRoot -ne $ExpectedStage)")
    replace_one(ROOT / 'tools/record_qa_routing_v3_version.ps1', '$Operation = Get-Content',
        "if ($Version -eq 'V24') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $ExecutionId = 'qa-routing-v24-20260916-r1'\n    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v24-20260916-r1'\n"
        "    $CommitMessage = 'fix: reuse verified latest readings and reject code offers [REQ-QA-LATEST-PREFETCH-REUSE-20260917] [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v24-20260916-r1]'\n"
        "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n    $OperationPath = Join-Path $StageRoot 'operation.json'\n    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    replace_one(ROOT / 'tools/remote_preflight_qa_routing_v3.ps1', "$Python = 'C:\\Program Files\\Python311\\python.exe'",
        "if ($Version -eq 'V24') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v24-20260916-r1' }\n$Python = 'C:\\Program Files\\Python311\\python.exe'")
    replace_one(ROOT / 'tools/prepare_qa_v9_invocations.py', '"v21", "v22", "v23")', '"v21", "v22", "v23", "v24")')
    replace_one(ROOT / 'tools/stage_qa_release.py', "'v21', 'v22', 'v23')", "'v21', 'v22', 'v23', 'v24')")
    replace_one(ROOT / 'tools/record_qa_release_preflight.py', "('v21','v22','v23')", "('v21','v22','v23','v24')")
    registry.write_bytes((json.dumps(recipes, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'targets': list(BASELINES), 'read_count': len(reads)}))


if __name__ == '__main__':
    main()
