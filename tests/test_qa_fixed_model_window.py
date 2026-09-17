"""Exercise the real window try/finally using isolated task/HTTP mocks, never production."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('window_batch', ROOT / 'tools/run_qa_template_batch.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)
PWSH = Path('C:/Program Files/PowerShell/7/pwsh.exe')
DIGEST = '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'
OTHER = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'


def test_deadline_blocks_before_claim_or_send(monkeypatch, tmp_path):
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'cases': [{'case_id': 'synthetic', 'prompt': 'synthetic'}], 'phase': 'synthetic'}))
    monkeypatch.setattr(sys, 'argv', ['batch', '--root', str(tmp_path), '--plan', str(plan),
                                    '--collector', str(tmp_path / 'collector.py'), '--output', str(tmp_path / 'output'),
                                    '--deadline-epoch', '100', '--execute'])
    monkeypatch.setattr(batch, 'verify', lambda *args: None)
    monkeypatch.setattr(batch.time, 'time', lambda: 1)
    monkeypatch.setattr(batch.subprocess, 'run', lambda *args, **kwargs: pytest.fail('Collector must not run'))
    batch.main()
    evidence = json.loads((tmp_path / 'output/progress.json').read_text())
    assert evidence['state'] == 'blocked' and evidence['requests'] == evidence['completed'] == 0
    assert not list((tmp_path / 'output').glob('*.claim'))


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_invalid_deadline_rejected(value):
    with pytest.raises(ValueError):
        batch.require_request_budget(value, now=0)


def test_deadline_reserves_full_collector_budget():
    batch.require_request_budget(301, now=0)
    with pytest.raises(RuntimeError, match='no next request sent'):
        batch.require_request_budget(300, now=0)


@pytest.mark.skipif(not PWSH.exists(), reason='PowerShell 7 is required for the real executor harness')
@pytest.mark.parametrize('mode,enabled,expected_error', [
    ('ok', True, False), ('ok', False, False), ('bad_resident', True, True),
    ('batch_error', True, True), ('disable_error', True, True), ('duplicate_pool', True, True)])
def test_real_window_restores_only_its_task(tmp_path, mode, enabled, expected_error):
    root = tmp_path / 'root'
    root.mkdir()
    stage = tmp_path / 'stage'
    stage.mkdir()
    plan = stage / 'templates.remaining.plan.json'
    plan.write_text(json.dumps({'cases': [{'case_id': f'synthetic-{i}', 'prompt': 'synthetic'} for i in range(822)],
                                'model_identity': {'name': 'chiqiongblastfuenace:latest', 'digest': OTHER,
                                                   'approved_digests': [DIGEST, DIGEST] if mode == 'duplicate_pool' else [DIGEST, OTHER]}}))
    fake = stage / 'batch.py'
    fake.write_text("import argparse,json,pathlib,sys\np=argparse.ArgumentParser()\np.add_argument('--root');p.add_argument('--plan');p.add_argument('--collector');p.add_argument('--output');p.add_argument('--deadline-epoch');p.add_argument('--execute',action='store_true')\na=p.parse_args()\nx=json.loads(pathlib.Path(a.plan).read_text(encoding='utf-8'))\nassert 'approved_digests' not in x['model_identity']\nassert x['model_identity']['digest']=='" + DIGEST + "'\n" + ("sys.exit(9)\n" if mode == 'batch_error' else "o=pathlib.Path(a.output);o.mkdir();(o/'progress.json').write_text(json.dumps({'state':'completed','completed':822,'requests':822}))\n"))
    collector = stage / 'collector.py'
    collector.write_text('# synthetic')
    source = (ROOT / 'tools/run_qa_fixed_model_window.ps1').read_text(encoding='utf-8')
    source = source.replace("F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW", root.as_posix())
    source = source.replace('C:/Users/Administrator/AppData/Local/Temp/qa-model-window-v26-20260917-r2', stage.as_posix())
    source = source.replace('C:/Program Files/Python311/python.exe', Path(sys.executable).as_posix())
    for name in ['Global\\BFQaFixedModelWindow', 'Global\\BFOllamaModelSwitch']:
        source = source.replace(name, 'Local\\Synthetic-' + uuid.uuid4().hex)
    window = stage / 'window.ps1'
    window.write_text(source, encoding='utf-8')
    calls = tmp_path / 'calls.json'
    harness = tmp_path / 'harness.ps1'
    header = r"""$ErrorActionPreference='Stop'
$global:Enabled=__ENABLED__
$global:Calls=[Collections.Generic.List[string]]::new()
function Check-Task($TaskPath,$TaskName) { if ($TaskPath -ne '\BlastFurnaceServices\' -or $TaskName -ne 'BFOllamaModelSelectionRecovery') { throw 'Other task forbidden' } }
function Get-ScheduledTask { param($TaskPath,$TaskName) Check-Task $TaskPath $TaskName; [pscustomobject]@{Settings=[pscustomobject]@{Enabled=$global:Enabled}} }
function Disable-ScheduledTask { param($TaskPath,$TaskName) Check-Task $TaskPath $TaskName; $global:Calls.Add('disable'); $global:Enabled=$false; __DISABLE__ }
function Enable-ScheduledTask { param($TaskPath,$TaskName) Check-Task $TaskPath $TaskName; $global:Calls.Add('enable'); $global:Enabled=$true }
function Invoke-RestMethod { param($Uri,$TimeoutSec) if ($Uri -notin @('http://127.0.0.1:11434/api/tags','http://127.0.0.1:11434/api/ps')) { throw 'Unexpected HTTP call' }; [pscustomobject]@{models=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest='__DIGEST__'})} }
function Start-Sleep { param($Seconds) }
$Failed=$false
try { & '__WINDOW__' -Stage '__STAGE__' -PlanHash '__PLAN__' -BatchHash '__BATCH__' -CollectorHash '__COLLECTOR__' -WindowMinutes 15 }
catch { $Failed=$true; $Message=$_.ToString() }
@{failed=$Failed; message=$Message; enabled=$global:Enabled; calls=@($global:Calls.ToArray())} | ConvertTo-Json | Set-Content -LiteralPath '__CALLS__' -Encoding utf8
"""
    values = {'ENABLED': '$true' if enabled else '$false', 'DISABLE': "throw 'synthetic disable failure'" if mode == 'disable_error' else '',
              'DIGEST': 'unapproved' if mode == 'bad_resident' else DIGEST, 'WINDOW': window.as_posix(),
              'STAGE': stage.as_posix(), 'CALLS': calls.as_posix()}
    values.update({name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in [('PLAN', plan), ('BATCH', fake), ('COLLECTOR', collector)]})
    for key, value in values.items():
        header = header.replace('__' + key + '__', value)
    harness.write_text(header, encoding='utf-8')
    result = subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-File', str(harness)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    outcome = json.loads(calls.read_text(encoding='utf-8-sig'))
    assert outcome['failed'] is expected_error, outcome
    assert outcome['enabled'] is enabled
    assert outcome['calls'] == (['disable', 'enable'] if enabled and mode != 'duplicate_pool' else [])
    if mode != 'duplicate_pool':
        audit = json.loads((root / 'logs/qa_model_window_v26_20260917_r2/window.json').read_text())
        assert audit['task_restored'] is True
        assert audit['automatic_replay'] is False
