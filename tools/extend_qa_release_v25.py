"""Register four-file clock/query/chart repair against verified V24 production."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

from extend_qa_release_v17 import replace_one

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '高炉前端数据/智能助手/backend/'
BASELINES = {
    'ollama_proxy_server.py': '2ba8dc4e6118490b6e6f2683314520bbfbc92fb47404ee9e8953769eb8dfd888',
    'qa_time_window_plan.py': '7c54df55a8c7042b8c8b623d8caed0872da948972ac803d8f899b5e520853720',
    'qa_task_plan.py': '0a1b950f221dcf90c03e1e623fe17453e7d3551ae2d9cf5bb789d9fd9c952d64',
    'qa_entity_resolution.py': '46c49bb5020425134133af14c51dd902b9e9c5a3787074012b03dd094a500c7a',
}


def main():
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v25' in recipes:
        raise ValueError('V25 already registered; inspect instead of rerunning')
    runtime = ROOT / '.codex_runtime/qa-routing-v25'
    baseline_dir = runtime / 'baseline'
    baseline_dir.mkdir(exist_ok=False)
    changes = []
    for name, expected in BASELINES.items():
        raw = ((ROOT / '.codex_runtime/qa-routing-v24/candidate' / name).read_bytes()
               if name == 'ollama_proxy_server.py' else subprocess.check_output(['git', 'show', 'HEAD:' + PREFIX + name], cwd=ROOT))
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Production baseline mismatch: ' + name)
        desired = (runtime / 'candidate' / name).read_bytes()
        (baseline_dir / name).write_bytes(raw)
        changes.extend(difflib.unified_diff(raw.decode().splitlines(True), desired.decode().splitlines(True),
            fromfile='production/' + name, tofile='candidate/' + name))
    (runtime / 'candidate.diff').write_bytes(''.join(changes).encode('utf-8'))
    reads = dict(recipes['v24']['read_files'])
    for name in BASELINES:
        reads.pop(PREFIX + name, None)
    reads.update({
        PREFIX + 'qa_verified_facts.py': '15a43e3909e6528faa71456a4a6ec97b8a9ad2e758d2863ae5d7b1b8ba64cfeb',
        PREFIX + 'qa_evidence_policy.py': '541545bc427892b61356bbb61821b0d8f6c67e150d91a067acc147d823aac8b4',
        '高炉前端数据/智能助手/mcp/gl02_static_pressure_points.json': '9cf54085b22b3111e9f244e31fc762fc002606845afa25d831b0e742365c68ec',
    })
    scripts = ['remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1',
        'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1']
    markers = {
        'ollama_proxy_server.py': ['REQ-QA-EXPLICIT-CLOCK-AND-CHART-20260917', 'qa_time_window_plan.format_history_answer'],
        'qa_time_window_plan.py': ['def parse_explicit_clock_range', 'def format_history_answer'],
        'qa_task_plan.py': ['qa_time_window_plan.explicit_clock_intent', '"画出来"'],
        'qa_entity_resolution.py': ['static_pressure_height_position_range', "'三个高度'"],
    }
    recipes['v25'] = {
        'artifacts': {name: {'baseline': [value], 'markers': markers[name], 'allow_create': False}
            for name, value in BASELINES.items()}, 'read_files': reads,
        'sources': ['tools/extend_qa_release_v25.py', 'tools/build_qa_v25_clock_chart_candidate.py',
            'tools/qa_routing_release_extensions.json', 'tools/prepare_qa_routing_v3_release.py',
            'tools/stage_qa_release.py', 'tools/prepare_qa_v9_invocations.py', 'tools/record_qa_release_preflight.py',
            *['tools/' + n for n in scripts], *[PREFIX + n for n in BASELINES if n != 'ollama_proxy_server.py'],
            'tests/test_qa_explicit_clock_chart.py', 'tests/test_qa_time_window_plan.py', 'tests/test_qa_task_plan.py',
            'tests/test_qa_entity_resolution.py', 'tests/test_qa_latest_reuse_and_code_offers.py',
            'tests/test_qa_evidence_policy.py', 'tests/test_qa_statistical_scope.py'],
        'validations': [
            {'id': 'focused-pytest', 'kind': 'deterministic', 'status': 'passed', 'evidence': '159 passed; actual proxy seams, exact historical data and 18-object charts, clock/no-live negatives'},
            {'id': 'final-luna-diff-review', 'kind': 'semantic', 'status': 'passed', 'evidence': 'gpt-5.6-luna low read-only review PASS; production baseline SHA and 490 unchanged proxy AST nodes'},
            {'id': 'remote-readonly-preflight', 'kind': 'readonly_remote', 'status': 'pending'},
        ],
    }
    for name in scripts:
        replace_one(ROOT / 'tools' / name, "'V21','V22','V23','V24')", "'V21','V22','V23','V24','V25')")
    allowed = ','.join("'" + PREFIX + name + "'" for name in BASELINES)
    replace_one(ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1', 'if ($StageRoot -ne $ExpectedStage)',
        "if ($Version -eq 'V25') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n    $Allowed = @(" + allowed + ")\n}\nif ($StageRoot -ne $ExpectedStage)")
    replace_one(ROOT / 'tools/record_qa_routing_v3_version.ps1', '$Operation = Get-Content',
        "if ($Version -eq 'V25') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $ExecutionId = 'qa-routing-v25-20260916-r1'\n    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v25-20260916-r1'\n"
        "    $CommitMessage = 'fix: preserve explicit historical windows and multi-height charts [REQ-QA-EXPLICIT-CLOCK-AND-CHART-20260917] [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v25-20260916-r1]'\n"
        "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n    $OperationPath = Join-Path $StageRoot 'operation.json'\n    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    replace_one(ROOT / 'tools/remote_preflight_qa_routing_v3.ps1', "$Python = 'C:\\Program Files\\Python311\\python.exe'",
        "if ($Version -eq 'V25') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v25-20260916-r1' }\n$Python = 'C:\\Program Files\\Python311\\python.exe'")
    replace_one(ROOT / 'tools/prepare_qa_v9_invocations.py', '"v21", "v22", "v23", "v24")', '"v21", "v22", "v23", "v24", "v25")')
    replace_one(ROOT / 'tools/stage_qa_release.py', "'v21', 'v22', 'v23', 'v24')", "'v21', 'v22', 'v23', 'v24', 'v25')")
    replace_one(ROOT / 'tools/record_qa_release_preflight.py', "('v21','v22','v23','v24')", "('v21','v22','v23','v24','v25')")
    registry.write_bytes((json.dumps(recipes, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'write_targets': list(BASELINES), 'read_count': len(reads)}))


if __name__ == '__main__':
    main()
