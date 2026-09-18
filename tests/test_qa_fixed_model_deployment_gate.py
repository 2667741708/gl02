"""Run the actual PowerShell metadata gate without model or service operations."""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = Path('C:/Program Files/PowerShell/7/pwsh.exe')
NAME = 'chiqiongblastfuenace:latest'
DIGEST = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
WRONG = '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'


def metadata(name=NAME, digest=DIGEST):
    return {'name': name, 'digest': digest}


def run_gate(tmp_path, responses, *, exception=False):
    text = (ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1').read_text(encoding='utf-8')
    function = 'function Assert-FixedModelIdentity {' + text.split('function Assert-FixedModelIdentity {', 1)[1].split('function Read-QaReadiness {', 1)[0]
    literal = json.dumps(responses).replace("'", "''")
    script = '\n'.join([
        "$ErrorActionPreference = 'Stop'",
        "if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell7 required' }",
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)",
        '$script:Calls = [Collections.Generic.List[object]]::new()',
        "$script:Responses = ConvertFrom-Json '" + literal + "'",
        'function Invoke-RestMethod {',
        ' param([string]$Method, [string]$Uri, [int]$TimeoutSec)',
        ' $index = $script:Calls.Count',
        ' $script:Calls.Add([pscustomobject]@{method=$Method;uri=$Uri;timeout=$TimeoutSec})',
        " throw 'Synthetic unavailable metadata'" if exception else ' return $script:Responses[$index]',
        '}', function,
        '$ok = $false; $errorType = $null',
        'try { Assert-FixedModelIdentity; $ok = $true } catch { $errorType = $_.Exception.GetType().Name }',
        '@{ok=$ok;calls=@($script:Calls.ToArray());error_type=$errorType} | ConvertTo-Json -Compress -Depth 8',
    ])
    path = tmp_path / 'actual-fixed-model-gate.ps1'
    path.write_bytes((script + '\n').encode('utf-8'))
    result = subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-File', str(path)],
        capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_matching_tags_resident_tags_pass_without_loading_or_switching(tmp_path):
    result = run_gate(tmp_path, [{'models': [metadata()]}] * 3)
    assert result['ok'] and result['error_type'] is None
    assert [r['uri'].rsplit('/', 1)[-1] for r in result['calls']] == ['tags', 'ps', 'tags']
    assert all(r['method'] == 'Get' and r['timeout'] == 5 for r in result['calls'])


@pytest.mark.parametrize('position,models', [
    (0, [metadata(digest=WRONG)]), (0, []), (0, [metadata(), metadata()]),
    (1, []), (1, [metadata(digest=WRONG)]), (1, [metadata(name='chiqiongblastfuenace:1')]),
    (1, [metadata(), metadata(name='nomic-embed-text:latest')]),
    (1, [metadata(), metadata(name='qwen3:latest')]), (1, [metadata(), metadata()]),
    (1, [{'name': NAME}]), (1, [metadata(name=NAME.upper())]),
    (2, [metadata(digest=WRONG)]), (2, []),
])
def test_missing_wrong_duplicate_extra_or_drifting_residency_fails_before_mutation(tmp_path, position, models):
    responses = [{'models': [metadata()]} for _ in range(3)]
    responses[position] = {'models': models}
    result = run_gate(tmp_path, responses)
    assert not result['ok'] and len(result['calls']) == position + 1
    assert all(r['method'] == 'Get' for r in result['calls'])


def test_metadata_failure_does_not_warm_retry_or_invoke_model(tmp_path):
    result = run_gate(tmp_path, [{'models': [metadata()]}] * 3, exception=True)
    assert not result['ok'] and len(result['calls']) == 1


def test_other_registered_tags_do_not_imply_another_resident_model(tmp_path):
    extra = [metadata(name='chiqiongblastfuenace:1'), metadata(name='nomic-embed-text:latest')]
    result = run_gate(tmp_path, [{'models': [metadata(), *extra]}, {'models': [metadata()]}, {'models': [metadata(), *extra]}])
    assert result['ok']


def test_fixed_identity_checked_before_stop_under_mutex_and_after_health():
    text = (ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1').read_text(encoding='utf-8')
    outside = text.index('\nAssert-FixedModelIdentity\n')
    assert outside < text.index('$Mutex = [Threading.Mutex]')
    lock = text.index('    Assert-FixedModelIdentity\n', outside)
    assert text.index('    Assert-Baselines\n', outside) < lock < text.index("    Service-Action 'stop'", lock)
    assert text.index('    $Readiness = Read-QaReadiness\n') < text.rindex('    Assert-FixedModelIdentity\n') < text.index('    $Result.ok=$true')
