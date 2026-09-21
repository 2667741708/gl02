"""Register exactly three chart/evidence targets against accepted V25 bytes."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

from extend_qa_release_v17 import replace_one

ROOT = Path(__file__).resolve().parents[1]
BACKEND = '高炉前端数据/智能助手/backend/'
MCP = '高炉前端数据/智能助手/mcp/'
BASELINES = {
    'ollama_proxy_server.py': (BACKEND, 'ef7b970caf748d8965eabdfbd308b988ebd1d47ba4c6b4a9cc8dbfb38db7ecf9'),
    'qa_tool_fallback.py': (BACKEND, '8d5c3737d463aa5990f844655d0925314eb77fc67a83c066e2a4bfd51c3043ab'),
    'bf_data_mcp_server.py': (MCP, '9dd1999e40e0a4648c25e4ae626b5e290269e68cab0e707bc4561fac4f9a3e95'),
}


def main():
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v26' in recipes:
        raise ValueError('V26 already registered; inspect rather than repeat')
    runtime = ROOT / '.codex_runtime/qa-routing-v26'
    base = runtime / 'baseline'
    base.mkdir(exist_ok=True)
    changes = []
    for name, (prefix, expected) in BASELINES.items():
        raw = ((ROOT / '.codex_runtime/qa-routing-v25/candidate' / name).read_bytes()
               if name == 'ollama_proxy_server.py' else (runtime / 'production-bf_data_mcp_server.py').read_bytes()
               if name == 'bf_data_mcp_server.py' else subprocess.check_output(['git', 'show', 'HEAD:' + prefix + name], cwd=ROOT))
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Baseline mismatch: ' + name)
        desired = (runtime / 'candidate' / name).read_bytes()
        (base / name).write_bytes(raw)
        changes.extend(difflib.unified_diff(raw.decode().splitlines(True), desired.decode().splitlines(True),
            fromfile='production/' + name, tofile='candidate/' + name))
    (runtime / 'candidate.diff').write_bytes(''.join(changes).encode('utf-8'))
    reads = dict(recipes['v25']['read_files'])
    for name, meta in recipes['v25']['artifacts'].items():
        reads[meta.get('relative') or BACKEND + name] = hashlib.sha256((ROOT / '.codex_runtime/qa-routing-v25/candidate' / name).read_bytes()).hexdigest()
    for name, (prefix, _) in BASELINES.items():
        reads.pop(prefix + name, None)
    scripts = ['remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1',
               'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1']
    markers = {'ollama_proxy_server.py': ['import qa_tool_fallback', 'qa_tool_fallback.model_result_text'],
               'qa_tool_fallback.py': ['qa-tool-fallback-v2', 'REQ-QA-CHART-COVERAGE-20260917'],
               'bf_data_mcp_server.py': ['REQ-QA-CHART-COVERAGE-20260917', '"covered_variables"', '未静默截断变量']}
    recipes['v26'] = {'artifacts': {name: {'relative': prefix + name, 'baseline': [value], 'markers': markers[name], 'allow_create': False}
                                       for name, (prefix, value) in BASELINES.items()},
                     'read_files': reads,
                     'sources': ['tools/extend_qa_release_v26.py', 'tools/build_qa_v26_chart_evidence_candidate.py',
                                 'tools/check_and_bind_qa_v26_preservation.py', 'tools/qa_routing_release_extensions.json',
                                 'tools/prepare_qa_routing_v3_release.py', 'tools/stage_qa_release.py', 'tools/prepare_qa_v9_invocations.py',
                                 'tools/record_qa_release_preflight.py', *['tools/' + n for n in scripts],
                                 BACKEND + 'qa_tool_fallback.py', MCP + 'bf_data_mcp_server.py', 'tests/test_qa_chart_evidence.py',
                                 'tests/test_qa_explicit_clock_chart.py', 'tests/test_qa_time_window_plan.py', 'tests/test_qa_task_plan.py',
                                 'tests/test_qa_entity_resolution.py', 'tests/test_qa_latest_reuse_and_code_offers.py',
                                 'tests/test_qa_evidence_policy.py', 'tests/test_qa_statistical_scope.py'],
                     'validations': [{'id': 'focused-pytest', 'kind': 'deterministic', 'status': 'passed', 'evidence': '174 passed; actual chart tool, full JSON batch, typed fallback and existing clock/no-live contracts'},
                                     {'id': 'final-luna-diff-review', 'kind': 'semantic', 'status': 'passed', 'evidence': 'gpt-5.6-luna low read-only PASS; four proxy functions and one import, 494 protected AST nodes'},
                                     {'id': 'remote-readonly-preflight', 'kind': 'readonly_remote', 'status': 'pending'}]}
    for name in scripts:
        replace_one(ROOT / 'tools' / name, "'V21','V22','V23','V24','V25')", "'V21','V22','V23','V24','V25','V26')")
    allowed = ','.join("'" + prefix + name + "'" for name, (prefix, _) in BASELINES.items())
    replace_one(ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1', 'if ($StageRoot -ne $ExpectedStage)',
        "if ($Version -eq 'V26') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n    $Allowed = @(" + allowed + ")\n}\nif ($StageRoot -ne $ExpectedStage)")
    replace_one(ROOT / 'tools/record_qa_routing_v3_version.ps1', '$Operation = Get-Content',
        "if ($Version -eq 'V26') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $ExecutionId = 'qa-routing-v26-20260916-r1'\n    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v26-20260916-r1'\n"
        "    $CommitMessage = 'fix: retain complete chart evidence and cover all requested points [REQ-QA-CHART-COVERAGE-20260917] [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v26-20260916-r1]'\n"
        "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n    $OperationPath = Join-Path $StageRoot 'operation.json'\n    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    replace_one(ROOT / 'tools/remote_preflight_qa_routing_v3.ps1', "$Python = 'C:\\Program Files\\Python311\\python.exe'",
        "if ($Version -eq 'V26') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v26-20260916-r1' }\n$Python = 'C:\\Program Files\\Python311\\python.exe'")
    for name, old, new in [('prepare_qa_v9_invocations.py', '"v24", "v25")', '"v24", "v25", "v26")'),
                           ('stage_qa_release.py', "'v24', 'v25')", "'v24', 'v25', 'v26')"),
                           ('record_qa_release_preflight.py', "'v24','v25')", "'v24','v25','v26')")]:
        replace_one(ROOT / 'tools' / name, old, new)
    registry.write_bytes((json.dumps(recipes, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'write_targets': list(BASELINES), 'read_count': len(reads)}))


if __name__ == '__main__':
    main()
