"""Prepare, without production writes, the proven-unsent V26 comparison window."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPROVED = ['9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb',
            'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(root=ROOT):
    runtime = root / '.codex_runtime/qa-routing-v26'
    previous = runtime / 'failure-round.plan.private.json'
    recovery = json.loads((runtime / 'readonly-recovery.json').read_text(encoding='utf-8'))
    if (recovery['plan_sha256'] != sha(previous) or not recovery['process_absent']
            or recovery['requests'] != 0 or recovery['completed'] != 0
            or recovery['claim_ids'] or recovery['result_ids']):
        raise ValueError('Unsent recovery not proven; never replay claimed or uncertain questions')
    plan = json.loads(previous.read_text(encoding='utf-8'))
    summary_path = root / 'tests/qa_regression/initial_semantic_summary_20260917.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    expected = {r['case_id']: r for r in summary['rows'] if r['status'] in {'failed', 'partial'}}
    ids = [r['case_id'] for r in plan['cases']]
    if (len(ids) != 822 or len(set(ids)) != 822 or set(ids) != set(expected)
            or 'TPL-10C8C8FAF2C694EF' in ids):
        raise ValueError('Unexpected cohort or uncertain original')
    if plan['initial_semantic_summary_sha256'] != sha(summary_path):
        raise ValueError('Initial scoring changed')
    for case in plan['cases']:
        original = expected[case['case_id']]
        if (hashlib.sha256(case['prompt'].encode('utf-8')).hexdigest() != original['original_prompt_sha256']
                or case['previous_result_sha256'] != original['original_result_sha256']):
            raise ValueError('Original question/result binding changed')
    record = json.loads((runtime / 'release/accepted-version-record.json').read_text(encoding='utf-8'))
    if not record['ok'] or record['head_after'] != plan['production_commit']:
        raise ValueError('Accepted version changed')
    folder = runtime / 'fixed-model-window-r2'
    folder.mkdir(exist_ok=False)
    plan.update(round='model-window-v26-20260917-r2', predecessor_frozen_plan_sha256=sha(previous),
                recovery_sha256=sha(runtime / 'readonly-recovery.json'),
                policy='All 822 original prompts proven unsent in V26 r1. Separate task-change authorization required. The window owner freezes the already-resident approved Qwen digest before sending. One POST per original; stop at deadline or identity drift. No automatic replay or continuation; claims and uncertain cases excluded on recovery.')
    plan['model_identity']['approved_digests'] = APPROVED
    plan['collector_sha256'] = sha(root / 'tools/run_qa_live_case.py')
    target = folder / 'templates.remaining.plan.json'
    target.write_bytes((json.dumps(plan, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    stage = 'C:/Users/Administrator/AppData/Local/Temp/qa-model-window-v26-20260917-r2'
    bindings = [(target, 'templates.remaining.plan.json'),
                (root / 'tools/run_qa_template_batch.py', 'batch.py'),
                (root / 'tools/run_qa_live_case.py', 'collector.py'),
                (root / 'tools/run_qa_fixed_model_window.ps1', 'window.ps1'),
                (root / 'tools/start_qa_fixed_model_window.ps1', 'start.ps1')]
    manifest = {'stage': stage, 'total': 822, 'production_commit': plan['production_commit'],
                'requires_separate_task_authorization': True, 'automatic_replay': False,
                'files': [{'local': str(p), 'remote': stage + '/' + name, 'sha256': sha(p)} for p, name in bindings]}
    (folder / 'upload.private.json').write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
    invoke = """[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8
[Console]::InputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$Starter = '__STAGE__/start.ps1'
if ((Get-FileHash -LiteralPath $Starter -Algorithm SHA256).Hash -ne '__START__') { throw 'Launcher hash changed' }
& $Starter -Stage '__STAGE__' -WindowHash '__WINDOW__' -PlanHash '__PLAN__' -BatchHash '__BATCH__' -CollectorHash '__COLLECTOR__' -WindowMinutes 120
"""
    for marker, value in [('STAGE', stage), ('START', sha(bindings[4][0])), ('WINDOW', sha(bindings[3][0])),
                          ('PLAN', sha(target)), ('BATCH', sha(bindings[1][0])), ('COLLECTOR', sha(bindings[2][0]))]:
        invoke = invoke.replace('__' + marker + '__', value)
    (folder / 'invoke-window.ps1').write_bytes(invoke.encode('utf-8'))
    return {'ok': True, 'total': 822, 'plan_sha256': sha(target), 'production_commit': plan['production_commit'],
            'requires_separate_task_authorization': True}


if __name__ == '__main__':
    print(json.dumps(freeze()))
